from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.models.voice_context import TenantVoiceContextField
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)
from app.schemas.public_voice_submissions import (
    PublicFieldError,
    PublicVoiceExperienceSubmissionRequest,
    PublicVoiceExperienceSubmissionResponse,
)
from app.services.crm_contact_service import CrmContactService
from app.services.crm_activity_service import CrmActivityService
from app.services.crm_lead_resolver_service import CrmLeadResolverService
from app.services.integration_event_service import IntegrationEventService
from app.services.public_voice_experience_service import (
    PublicVoiceExperienceService,
    PublicVoiceSnapshot,
)
from app.services.voice_phone_service import (
    VoicePhoneValidationError,
    normalize_caller_id,
    normalize_outbound_phone,
)
from app.services.voice_sip_route_service import VoiceSipRouteService


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9() .-]{7,32}$")
STRING_TYPES = {"text", "textarea", "email", "phone", "select", "date"}
SUPPORTED_RULES = {"min_length", "max_length", "min", "max"}
STRING_MAX_LENGTHS = {"text": 200, "textarea": 5000, "email": 254, "phone": 32}
INTEGER_MIN = -1_000_000_000
INTEGER_MAX = 1_000_000_000


class ExperienceVersionChanged(Exception):
    pass


class SubmissionValidationFailed(Exception):
    def __init__(self, fields: list[PublicFieldError] | None = None) -> None:
        self.fields = fields or []


class HistoricalValidationConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class PersistedSubmission:
    response: PublicVoiceExperienceSubmissionResponse
    submission_id: str
    tenant_id: str
    experience_id: str
    version: int
    answers: dict[str, str | int | bool | None]
    fields: list[TenantVoiceContextField]
    default_country: str


class PublicVoiceSubmissionService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.session_factory = session_factory
        self.ttl_seconds = ttl_seconds

    def pre_resolve(self, slug: str) -> PublicVoiceSnapshot:
        with self.session_factory() as db:
            return PublicVoiceExperienceService(db)._resolve_snapshot(slug)

    def persist(
        self,
        slug: str,
        payload: PublicVoiceExperienceSubmissionRequest,
    ) -> PersistedSubmission:
        context_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(context_token.encode()).hexdigest()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        with self.session_factory() as db:
            with db.begin():
                snapshot = PublicVoiceExperienceService(db)._resolve_snapshot(
                    slug, for_update=True
                )
                if snapshot.version.version != payload.version:
                    raise ExperienceVersionChanged
                call_settings = snapshot.version.call_settings_json
                allowed_countries = None
                if call_settings.get("mode") in ("callback", "both"):
                    route = VoiceSipRouteService(db).get_route(
                        snapshot.experience.tenant_id
                    )
                    if route is not None and route.allowed_countries_json:
                        allowed_countries = frozenset(route.allowed_countries_json)
                errors = validate_submission(
                    payload, snapshot, allowed_countries=allowed_countries
                )
                if errors:
                    raise SubmissionValidationFailed(errors)
                answers = dict(payload.answers)
                phone_key = call_settings.get("phone_field_key")
                if call_settings.get("mode") in ("callback", "both") and isinstance(
                    answers.get(phone_key), str
                ):
                    phone_kwargs = {"default_country": call_settings.get("default_country")}
                    if allowed_countries is not None:
                        phone_kwargs["allowed_countries"] = allowed_countries
                    answers[phone_key] = normalize_outbound_phone(
                        answers[phone_key], **phone_kwargs
                    ).e164

                submission = TenantVoiceExperienceSubmission(
                    tenant_id=snapshot.experience.tenant_id,
                    experience_id=snapshot.experience.id,
                    experience_version_id=snapshot.version.id,
                    context_schema_id=snapshot.version.context_schema_id,
                    version=snapshot.version.version,
                    locale=payload.locale,
                    consent_accepted=payload.consent,
                    consent_accepted_at=now if payload.consent else None,
                )
                db.add(submission)
                db.flush()

                field_by_key = {field.key: field for field in snapshot.fields}
                db.add_all(
                    [
                        TenantVoiceExperienceSubmissionValue(
                            tenant_id=snapshot.experience.tenant_id,
                            submission_id=submission.id,
                            field_key=key,
                            field_type=field_by_key[key].field_type,
                            value_json=value,
                        )
                        for key, value in answers.items()
                        if value is not None
                    ]
                )
                db.add(
                    TenantVoiceContextSession(
                        tenant_id=snapshot.experience.tenant_id,
                        submission_id=submission.id,
                        experience_id=snapshot.experience.id,
                        experience_version_id=snapshot.version.id,
                        context_schema_id=snapshot.version.context_schema_id,
                        token_hash=token_hash,
                        expires_at=expires_at,
                    )
                )

            persisted = PersistedSubmission(
                response=PublicVoiceExperienceSubmissionResponse(
                    context_token=context_token,
                    expires_at=expires_at,
                ),
                submission_id=submission.id,
                tenant_id=snapshot.experience.tenant_id,
                experience_id=snapshot.experience.id,
                version=snapshot.version.version,
                answers=answers,
                fields=list(snapshot.fields),
                default_country=call_settings.get("default_country") or "CO",
            )

        self._project_to_crm(persisted)
        return persisted

    def _project_to_crm(self, persisted: PersistedSubmission) -> None:
        def first_answer(field_type: str) -> str | None:
            for field in persisted.fields:
                value = persisted.answers.get(field.key)
                if field.field_type == field_type and type(value) is str:
                    return value.strip()
            return None

        email_value = first_answer("email")
        phone_value = first_answer("phone")
        email = (
            email_value
            if email_value and EMAIL_RE.fullmatch(email_value)
            else None
        )
        # Submissions accept phones without a leading "+" (e.g. a bare local
        # number). CrmContactService.normalize_phone() only special-cases
        # 10-digit Colombian numbers, so pre-format using the experience's
        # own default_country here; fall back to the raw value if it can't
        # be parsed so a valid-but-unusual phone doesn't silently drop the
        # lead.
        phone = None
        if phone_value and PHONE_RE.fullmatch(phone_value):
            try:
                phone = normalize_caller_id(
                    phone_value, default_country=persisted.default_country
                )
            except VoicePhoneValidationError:
                phone = phone_value
        name_value = persisted.answers.get("full_name")
        company_value = persisted.answers.get("company")
        name = name_value.strip() or None if type(name_value) is str else None
        company = company_value.strip() or None if type(company_value) is str else None
        status = "skipped"
        event_metadata = {
            "experience_id": persisted.experience_id,
            "version": persisted.version,
        }

        with self.session_factory() as db:
            try:
                if email or phone:
                    contact = CrmContactService(db).get_or_create_contact(
                        tenant_id=persisted.tenant_id,
                        phone=phone,
                        email=email,
                        name=name,
                        metadata={"company": company, "source": "voice_experience"},
                    )
                    lead = CrmLeadResolverService(db).resolve_or_create_lead_for_new_context(
                        persisted.tenant_id,
                        contact,
                        {"context_id": persisted.submission_id, "source": "voice_experience"},
                    )
                    CrmActivityService(db).create_activity(
                        tenant_id=persisted.tenant_id,
                        lead_id=lead.id,
                        contact_id=contact.id,
                        activity_type="voice_experience_submitted",
                        title="Voice experience submitted",
                        deduplication_key=f"voice_experience_submission:{persisted.submission_id}",
                        payload_json={
                            "context_id": persisted.submission_id,
                            **event_metadata,
                        },
                    )
                    submission = db.get(
                        TenantVoiceExperienceSubmission, persisted.submission_id
                    )
                    if submission is None:
                        raise RuntimeError("voice submission disappeared")
                    submission.crm_contact_id = contact.id
                    submission.crm_lead_id = lead.id
                    db.commit()
                    status = "success"
                IntegrationEventService(db).record_event(
                    tenant_id=persisted.tenant_id,
                    provider="voice",
                    event_type="voice_experience_submission_crm",
                    status=status,
                    resource_type="voice_experience_submission",
                    resource_id=persisted.submission_id,
                    metadata=event_metadata,
                )
            except Exception:
                db.rollback()
                try:
                    IntegrationEventService(db).record_event(
                        tenant_id=persisted.tenant_id,
                        provider="voice",
                        event_type="voice_experience_submission_crm",
                        status="failed",
                        resource_type="voice_experience_submission",
                        resource_id=persisted.submission_id,
                        metadata=event_metadata,
                    )
                except Exception:
                    db.rollback()


def validate_submission(
    payload: PublicVoiceExperienceSubmissionRequest,
    snapshot: PublicVoiceSnapshot,
    *,
    allowed_countries: frozenset[str] | None = None,
) -> list[PublicFieldError]:
    errors: list[PublicFieldError] = []
    fields = {field.key: field for field in snapshot.fields}
    for key in payload.answers.keys() - fields.keys():
        errors.append(PublicFieldError(key=key, code="unknown_field"))

    for key, field in fields.items():
        present = key in payload.answers
        value = payload.answers.get(key)
        if field.required and (
            not present or value is None or (type(value) is str and not value.strip())
        ):
            errors.append(PublicFieldError(key=key, code="required"))
            continue
        if not present or value is None:
            continue

        if field.field_type in STRING_TYPES and type(value) is not str:
            errors.append(PublicFieldError(key=key, code="invalid_type"))
            continue
        if field.field_type == "integer" and type(value) is not int:
            errors.append(PublicFieldError(key=key, code="invalid_type"))
            continue
        if field.field_type == "checkbox" and type(value) is not bool:
            errors.append(PublicFieldError(key=key, code="invalid_type"))
            continue

        rules = _validated_rules(field)
        if type(value) is str:
            if "min_length" in rules and len(value) < rules["min_length"]:
                errors.append(PublicFieldError(key=key, code="too_short"))
            global_max = STRING_MAX_LENGTHS.get(field.field_type)
            if (
                global_max is not None and len(value) > global_max
            ) or ("max_length" in rules and len(value) > rules["max_length"]):
                errors.append(PublicFieldError(key=key, code="too_long"))
        if type(value) is int:
            if (
                value < INTEGER_MIN
                or value > INTEGER_MAX
                or ("min" in rules and value < rules["min"])
                or ("max" in rules and value > rules["max"])
            ):
                errors.append(PublicFieldError(key=key, code="invalid_format"))

        if field.field_type == "select" and value not in {
            option.get("value") for option in field.options_json if isinstance(option, dict)
        }:
            errors.append(PublicFieldError(key=key, code="invalid_option"))
        elif field.field_type == "email" and not EMAIL_RE.fullmatch(value.strip()):
            errors.append(PublicFieldError(key=key, code="invalid_format"))
        elif field.field_type == "phone":
            call_settings = snapshot.version.call_settings_json
            if call_settings.get("mode") in ("callback", "both") and key == call_settings.get(
                "phone_field_key"
            ):
                try:
                    phone_kwargs = {"default_country": call_settings.get("default_country")}
                    if allowed_countries is not None:
                        phone_kwargs["allowed_countries"] = allowed_countries
                    normalize_outbound_phone(value, **phone_kwargs)
                except ValueError:
                    errors.append(PublicFieldError(key=key, code="invalid_format"))
            elif not PHONE_RE.fullmatch(value.strip()):
                errors.append(PublicFieldError(key=key, code="invalid_format"))
        elif field.field_type == "date":
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d")
                if not 1900 <= parsed.year <= 2100:
                    raise ValueError
            except ValueError:
                errors.append(PublicFieldError(key=key, code="invalid_format"))

    consent = snapshot.version.consent_json
    if consent.get("required") is True and payload.consent is not True:
        errors.append(PublicFieldError(key="consent", code="consent_required"))
    return errors


def _validated_rules(field: TenantVoiceContextField) -> dict[str, int]:
    raw = field.validation_json
    if not isinstance(raw, dict):
        raise HistoricalValidationConfigurationError
    rules: dict[str, int] = {}
    for name in SUPPORTED_RULES:
        if name not in raw:
            continue
        value = raw[name]
        if type(value) is not int or (
            name in {"min_length", "max_length"} and value < 0
        ):
            raise HistoricalValidationConfigurationError
        rules[name] = value
    if (
        "min_length" in rules
        and "max_length" in rules
        and rules["min_length"] > rules["max_length"]
    ) or ("min" in rules and "max" in rules and rules["min"] > rules["max"]):
        raise HistoricalValidationConfigurationError
    return rules
