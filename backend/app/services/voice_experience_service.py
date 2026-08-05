from __future__ import annotations

import secrets
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.voice_context import TenantVoiceContextSchema
from app.models.voice_experiences import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.schemas.tenant_features import VoiceExperienceLimits
from app.schemas.voice_experiences import (
    VoiceExperienceResponse,
    VoiceExperienceVersionResponse,
    VoiceExperienceWriteRequest,
)
from app.services.tenant_feature_service import VOICE_EXPERIENCES, TenantFeatureService
from app.services.voice_agent_service import VoiceAgentService

VERSION_CONSTRAINT = "uq_tenant_voice_experience_versions_experience_version"
SLUG_CONSTRAINT = "uq_tenant_voice_experiences_slug"


class VoiceExperienceNotFoundError(ValueError):
    pass


class VoiceExperienceConflictError(ValueError):
    pass


class VoiceExperienceValidationError(ValueError):
    pass


def _constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def _matches_constraint(exc: IntegrityError, name: str, sqlite_columns: str) -> bool:
    if _constraint_name(exc) == name:
        return True
    message = str(exc.orig)
    return name in message or f"UNIQUE constraint failed: {sqlite_columns}" in message


class VoiceExperienceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = TenantFeatureService(db)
        self.agent_service = VoiceAgentService(db)

    def list_experiences(self, tenant_id: str) -> list[VoiceExperienceResponse]:
        self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        experiences = self.db.scalars(
            select(TenantVoiceExperience)
            .where(TenantVoiceExperience.tenant_id == tenant_id)
            .order_by(TenantVoiceExperience.created_at.desc())
        ).all()
        return [self.response(item) for item in experiences]

    def get_experience(self, tenant_id: str, experience_id: str) -> TenantVoiceExperience:
        self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        experience = self.db.scalar(
            select(TenantVoiceExperience).where(
                TenantVoiceExperience.id == experience_id,
                TenantVoiceExperience.tenant_id == tenant_id,
            )
        )
        if experience is None:
            raise VoiceExperienceNotFoundError("Voice experience not found.")
        return experience

    def create_experience(
        self,
        tenant_id: str,
        body: VoiceExperienceWriteRequest,
        user_id: str | None,
    ) -> TenantVoiceExperience:
        grant = self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        self._require_relations(tenant_id, body.agent_config_id, body.context_schema_id)
        count = self.db.scalar(
            select(func.count(TenantVoiceExperience.id)).where(
                TenantVoiceExperience.tenant_id == tenant_id,
                TenantVoiceExperience.status != "archived",
            )
        ) or 0
        limits = VoiceExperienceLimits.model_validate(grant.limits_json)
        if count >= limits.max_experiences:
            raise VoiceExperienceValidationError("Maximum voice experiences limit reached.")
        experience = TenantVoiceExperience(
            tenant_id=tenant_id,
            slug=secrets.token_urlsafe(24),
            status="draft",
            created_by_user_id=user_id,
            **self._draft_values(body),
        )
        self.db.add(experience)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _matches_constraint(exc, SLUG_CONSTRAINT, "tenant_voice_experiences.slug"):
                raise VoiceExperienceConflictError("Could not allocate a unique experience slug.") from exc
            raise
        self.db.refresh(experience)
        return experience

    def update_experience(
        self,
        tenant_id: str,
        experience_id: str,
        body: VoiceExperienceWriteRequest,
    ) -> TenantVoiceExperience:
        experience = self.get_experience(tenant_id, experience_id)
        self._ensure_mutable(experience)
        self._require_relations(tenant_id, body.agent_config_id, body.context_schema_id)
        for key, value in self._draft_values(body).items():
            setattr(experience, key, value)
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def publish_experience(
        self, tenant_id: str, experience_id: str, user_id: str | None
    ) -> TenantVoiceExperience:
        experience = self._locked_experience(tenant_id, experience_id)
        self._ensure_mutable(experience)
        if experience.status == "published":
            raise VoiceExperienceConflictError("Voice experience is already published.")
        _, schema = self._require_relations(
            tenant_id, experience.agent_config_id, experience.context_schema_id
        )
        if schema.status != "active":
            raise VoiceExperienceValidationError("Only an active context schema can be published.")
        next_version = (
            self.db.scalar(
                select(func.max(TenantVoiceExperienceVersion.version)).where(
                    TenantVoiceExperienceVersion.experience_id == experience.id
                )
            )
            or 0
        ) + 1
        now = datetime.now(timezone.utc)
        version = TenantVoiceExperienceVersion(
            experience_id=experience.id,
            tenant_id=tenant_id,
            version=next_version,
            agent_config_id=experience.agent_config_id,
            context_schema_id=experience.context_schema_id,
            name=experience.name,
            slug=experience.slug,
            default_locale=experience.default_locale,
            content_json=deepcopy(experience.content_json),
            theme_json=deepcopy(experience.theme_json),
            consent_json=deepcopy(experience.consent_json),
            call_settings_json=deepcopy(experience.call_settings_json),
            published_at=now,
            published_by_user_id=user_id,
            created_at=now,
        )
        self.db.add(version)
        try:
            self.db.flush()
            experience.status = "published"
            experience.published_version_id = version.id
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _matches_constraint(
                exc,
                VERSION_CONSTRAINT,
                "tenant_voice_experience_versions.experience_id, tenant_voice_experience_versions.version",
            ):
                raise VoiceExperienceConflictError("A concurrent publication already won.") from exc
            raise
        self.db.refresh(experience)
        return experience

    def unpublish_experience(
        self, tenant_id: str, experience_id: str
    ) -> TenantVoiceExperience:
        experience = self._locked_experience(tenant_id, experience_id)
        self._ensure_mutable(experience)
        if experience.status != "published":
            raise VoiceExperienceConflictError("Only a published experience can be unpublished.")
        experience.status = "unpublished"
        experience.published_version_id = None
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def archive_experience(
        self, tenant_id: str, experience_id: str
    ) -> TenantVoiceExperience:
        experience = self._locked_experience(tenant_id, experience_id)
        self._ensure_mutable(experience)
        if experience.status == "published":
            raise VoiceExperienceConflictError(
                "A published experience must be unpublished before archiving."
            )
        experience.status = "archived"
        experience.archived_at = datetime.now(timezone.utc)
        experience.published_version_id = None
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def list_versions(
        self, tenant_id: str, experience_id: str
    ) -> list[VoiceExperienceVersionResponse]:
        self.get_experience(tenant_id, experience_id)
        versions = self.db.scalars(
            select(TenantVoiceExperienceVersion)
            .where(
                TenantVoiceExperienceVersion.experience_id == experience_id,
                TenantVoiceExperienceVersion.tenant_id == tenant_id,
            )
            .order_by(TenantVoiceExperienceVersion.version.desc())
        ).all()
        return [self.version_response(item) for item in versions]

    def _locked_experience(
        self, tenant_id: str, experience_id: str
    ) -> TenantVoiceExperience:
        self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        experience = self.db.scalar(
            select(TenantVoiceExperience)
            .where(
                TenantVoiceExperience.id == experience_id,
                TenantVoiceExperience.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if experience is None:
            raise VoiceExperienceNotFoundError("Voice experience not found.")
        return experience

    def _require_relations(
        self, tenant_id: str, agent_config_id: str, schema_id: str
    ):
        try:
            agent = self.agent_service.validate_agent_belongs_to_tenant(
                tenant_id, agent_config_id
            )
        except ValueError as exc:
            raise VoiceExperienceNotFoundError(str(exc)) from exc
        schema = self.db.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
        )
        if schema is None:
            raise VoiceExperienceNotFoundError("Voice context schema not found.")
        if schema.agent_config_id != agent.id:
            raise VoiceExperienceValidationError(
                "Voice context schema does not belong to the selected voice agent."
            )
        return agent, schema

    @staticmethod
    def _ensure_mutable(experience: TenantVoiceExperience) -> None:
        if experience.status == "archived":
            raise VoiceExperienceConflictError("Archived voice experiences are immutable.")

    @staticmethod
    def _draft_values(body: VoiceExperienceWriteRequest) -> dict:
        payload = body.model_dump(mode="json")
        return {
            "agent_config_id": payload["agent_config_id"],
            "context_schema_id": payload["context_schema_id"],
            "name": payload["name"],
            "default_locale": payload["default_locale"],
            "content_json": payload["content"],
            "theme_json": payload["theme"],
            "consent_json": payload["consent"],
            "call_settings_json": payload["call_settings"],
        }

    @staticmethod
    def response(experience: TenantVoiceExperience) -> VoiceExperienceResponse:
        return VoiceExperienceResponse(
            id=experience.id,
            agent_config_id=experience.agent_config_id,
            context_schema_id=experience.context_schema_id,
            name=experience.name,
            slug=experience.slug,
            status=experience.status,
            default_locale=experience.default_locale,
            content=experience.content_json,
            theme=experience.theme_json,
            consent=experience.consent_json,
            call_settings=experience.call_settings_json,
            published_version_id=experience.published_version_id,
            archived_at=experience.archived_at,
            created_at=experience.created_at,
            updated_at=experience.updated_at,
        )

    @staticmethod
    def version_response(
        version: TenantVoiceExperienceVersion,
    ) -> VoiceExperienceVersionResponse:
        return VoiceExperienceVersionResponse(
            id=version.id,
            experience_id=version.experience_id,
            version=version.version,
            agent_config_id=version.agent_config_id,
            context_schema_id=version.context_schema_id,
            name=version.name,
            slug=version.slug,
            default_locale=version.default_locale,
            content=version.content_json,
            theme=version.theme_json,
            consent=version.consent_json,
            call_settings=version.call_settings_json,
            published_at=version.published_at,
            created_at=version.created_at,
        )
