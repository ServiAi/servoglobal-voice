from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.schemas.public_voice_experiences import (
    PublicCapabilities,
    PublicFieldOption,
    PublicVoiceConsent,
    PublicVoiceContent,
    PublicVoiceContextField,
    PublicVoiceExperienceResponse,
    PublicVoiceTheme,
)
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService


PUBLIC_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PUBLIC_FIELD_MODES = ("ask_if_missing", "prefill_and_confirm", "trust_prefill")


class PublicExperienceNotFound(Exception):
    pass


class PublicVoiceExperienceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = TenantFeatureService(db)

    def resolve(self, slug: str) -> PublicVoiceExperienceResponse:
        if not PUBLIC_SLUG_RE.fullmatch(slug):
            raise PublicExperienceNotFound

        experience = self.db.scalar(
            select(TenantVoiceExperience).where(TenantVoiceExperience.slug == slug)
        )
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

        return PublicVoiceExperienceResponse(
            slug=version.slug,
            locale=version.default_locale,
            version=version.version,
            content=self._content(version.content_json),
            theme=self._theme(version.theme_json),
            consent=self._consent(version.consent_json),
            fields=[self._field(field) for field in fields],
            capabilities=PublicCapabilities(),
        )

    @staticmethod
    def _content(payload: dict) -> PublicVoiceContent:
        return PublicVoiceContent.model_validate(
            {key: payload.get(key) for key in PublicVoiceContent.model_fields}
        )

    @staticmethod
    def _theme(payload: dict) -> PublicVoiceTheme:
        return PublicVoiceTheme.model_validate(
            {key: payload.get(key) for key in PublicVoiceTheme.model_fields}
        )

    @staticmethod
    def _consent(payload: dict) -> PublicVoiceConsent:
        return PublicVoiceConsent.model_validate(
            {key: payload.get(key) for key in PublicVoiceConsent.model_fields}
        )

    @staticmethod
    def _field(field: TenantVoiceContextField) -> PublicVoiceContextField:
        return PublicVoiceContextField(
            key=field.key,
            label=field.label,
            description=field.description,
            field_type=field.field_type,
            required=field.required,
            options=[
                PublicFieldOption(value=option["value"], label=option["label"])
                for option in field.options_json
            ]
            if field.field_type == "select"
            else [],
        )
