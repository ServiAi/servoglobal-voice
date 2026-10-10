from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.voice_experiences.application.contracts import Command, View

from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField, TenantVoiceContextSchema
from app.modules.voice_experiences.infrastructure.experience_models import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.modules.identity.public import VOICE_EXPERIENCES, FeatureFlags
from app.modules.telephony.public import SipRouteFacade

from app.modules.voice_experiences.domain.limits import PUBLIC_CONTEXT_COLLECTION_MODES

PUBLIC_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PUBLIC_FIELD_MODES = tuple(sorted(PUBLIC_CONTEXT_COLLECTION_MODES))
CALL_SETTINGS_FIELDS = frozenset({
    "auto_start", "show_microphone_help", "language", "mode",
    "phone_field_key", "default_country", "allowed_countries",
})


class PublicExperienceNotFound(Exception):
    pass


@dataclass(frozen=True)
class PublicVoiceSnapshot:
    experience: TenantVoiceExperience
    version: TenantVoiceExperienceVersion
    schema: TenantVoiceContextSchema
    fields: list[TenantVoiceContextField]


class PublicVoiceExperienceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = FeatureFlags(db)

    def resolve(self, slug: str) -> View:
        snapshot = self._resolve_snapshot(slug)
        version = snapshot.version
        call_settings = {
            key: version.call_settings_json.get(key)
            for key in CALL_SETTINGS_FIELDS
            if key in version.call_settings_json
        }
        calls_available = True
        raw_mode = call_settings.get("mode", "webrtc")
        if raw_mode in ("callback", "both"):
            try:
                route = SipRouteFacade(self.db).get_active_route(
                    snapshot.experience.tenant_id
                )
                call_settings["allowed_countries"] = list(route.allowed_countries)
            except Exception:
                call_settings["allowed_countries"] = []
                if raw_mode == "callback":
                    calls_available = False
                else:
                    # Callback needs an active outbound route; WebRTC does not,
                    # so degrade to WebRTC-only instead of hiding calls entirely.
                    call_settings["mode"] = "webrtc"

        return View(
            slug=version.slug,
            locale=version.default_locale,
            version=version.version,
            content=self._content(version.content_json),
            theme=self._theme(version.theme_json),
            consent=self._consent(version.consent_json),
            fields=[self._field(field) for field in snapshot.fields],
            call_settings=View(**call_settings),
            capabilities=View(calls=calls_available),
        )

    def _resolve_snapshot(
        self, slug: str, for_update: bool = False
    ) -> PublicVoiceSnapshot:
        if not PUBLIC_SLUG_RE.fullmatch(slug):
            raise PublicExperienceNotFound

        experience_query = select(TenantVoiceExperience).where(
            TenantVoiceExperience.slug == slug
        )
        if for_update:
            experience_query = experience_query.with_for_update()
        experience = self.db.scalar(experience_query)
        if (
            experience is None
            or experience.status != "published"
            or experience.published_version_id is None
            or not self.feature_service.is_enabled(
                experience.tenant_id, VOICE_EXPERIENCES
            )
        ):
            raise PublicExperienceNotFound

        version = self.db.scalar(
            select(TenantVoiceExperienceVersion).where(
                TenantVoiceExperienceVersion.id == experience.published_version_id,
                TenantVoiceExperienceVersion.experience_id == experience.id,
                TenantVoiceExperienceVersion.tenant_id == experience.tenant_id,
            )
        )
        if version is None:
            raise PublicExperienceNotFound

        schema = self.db.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == version.context_schema_id,
                TenantVoiceContextSchema.tenant_id == version.tenant_id,
            )
        )
        if schema is None:
            raise PublicExperienceNotFound

        fields = self.db.scalars(
            select(TenantVoiceContextField)
            .where(
                TenantVoiceContextField.tenant_id == version.tenant_id,
                TenantVoiceContextField.schema_id == schema.id,
                TenantVoiceContextField.collection_mode.in_(PUBLIC_FIELD_MODES),
            )
            .order_by(TenantVoiceContextField.position)
        ).all()

        return PublicVoiceSnapshot(
            experience=experience,
            version=version,
            schema=schema,
            fields=list(fields),
        )

    @staticmethod
    def _content(payload: dict) -> View:
        return View(**payload)

    @staticmethod
    def _theme(payload: dict) -> View:
        return View(**payload)

    @staticmethod
    def _consent(payload: dict) -> View:
        return View(**payload)

    @staticmethod
    def _field(field: TenantVoiceContextField) -> View:
        return View(
            key=field.key,
            label=field.label,
            description=field.description,
            field_type=field.field_type,
            required=field.required,
            options=[
                View(value=option["value"], label=option["label"])
                for option in field.options_json
            ]
            if field.field_type == "select"
            else [],
        )
