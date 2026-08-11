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
from app.services.integration_event_service import IntegrationEventService
from app.services.public_voice_experience_service import (
    PublicVoiceExperienceService,
    PublicVoiceSnapshot,
)


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9() .-]{7,32}$")
LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
STRING_TYPES = {"text", "textarea", "email", "phone", "select", "date"}
SUPPORTED_RULES = {"min_length", "max_length", "min", "max"}


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
    answers: dict[str, str | int | bool | None]
    fields: list[TenantVoiceContextField]


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
                errors = validate_submission(payload, snapshot)
                if errors:
                    raise SubmissionValidationFailed(errors)

                submission = TenantVoiceExperienceSubmission(
                    tenant_id=snapshot.experience.tenant_id,
                    experience_id=snapshot.experience.id,
                    experience_version_id=snapshot.version.id,
                    context_schema_id=snapshot.version.context_schema_id,
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
                            submission_id=submission.id,
                            field_key=key,
                            field_type=field_by_key[key].field_type,
                            value_json=value,
                        )
                        for key, value in payload.answers.items()
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
                answers=dict(payload.answers),
                fields=list(snapshot.fields),
            )

        self._project_to_crm(persisted)
        return persisted

    def _project_to_crm(self, persisted: PersistedSubmission) -> None:
        field_types = {field.key: field.field_type for field in persisted.fields}
        email_value = persisted.answers.get("email")
        phone_value = persisted.answers.get("phone")
        email = (
            email_value
            if field_types.get("email") == "email"
            and type(email_value) is str
            and EMAIL_RE.fullmatch(email_value.strip())
            else None
        )
        phone = (
            phone_value
            if field_types.get("phone") == "phone"
            and type(phone_value) is str
            and phone_value.strip().startswith("+")
            and PHONE_RE.fullmatch(phone_value.strip())
            else None
        )
        name_value = persisted.answers.get("full_name")
        company_value = persisted.answers.get("company")
        name = name_value if type(name_value) is str else None
        company = company_value if type(company_value) is str else None
        status = "skipped"

        with self.session_factory() as db:
            try:
                if email or phone:
                    CrmContactService(db).get_or_create_contact(
                        tenant_id=persisted.tenant_id,
                        phone=phone,
                        email=email,
                        name=name,
                        metadata={"company": company, "source": "voice_experience"},
                    )
                    status = "success"
                IntegrationEventService(db).record_event(
                    tenant_id=persisted.tenant_id,
                    provider="voice",
                    event_type="voice_experience_submission_crm",
                    status=status,
                    resource_type="voice_experience_submission",
                    resource_id=persisted.submission_id,
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
                    )
                except Exception:
                    db.rollback()


def validate_submission(
    payload: PublicVoiceExperienceSubmissionRequest,
    snapshot: PublicVoiceSnapshot,
) -> list[PublicFieldError]:
    errors: list[PublicFieldError] = []
    if not LOCALE_RE.fullmatch(payload.locale):
        errors.append(PublicFieldError(key="locale", code="invalid_format"))

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
            if "max_length" in rules and len(value) > rules["max_length"]:
                errors.append(PublicFieldError(key=key, code="too_long"))
        if type(value) is int:
            if "min" in rules and value < rules["min"]:
                errors.append(PublicFieldError(key=key, code="invalid_format"))
            if "max" in rules and value > rules["max"]:
                errors.append(PublicFieldError(key=key, code="invalid_format"))

        if field.field_type == "select" and value not in {
            option.get("value") for option in field.options_json if isinstance(option, dict)
        }:
            errors.append(PublicFieldError(key=key, code="invalid_option"))
        elif field.field_type == "email" and not EMAIL_RE.fullmatch(value.strip()):
            errors.append(PublicFieldError(key=key, code="invalid_format"))
        elif field.field_type == "phone" and not PHONE_RE.fullmatch(value.strip()):
            errors.append(PublicFieldError(key=key, code="invalid_format"))
        elif field.field_type == "date":
            try:
                datetime.strptime(value, "%Y-%m-%d")
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
