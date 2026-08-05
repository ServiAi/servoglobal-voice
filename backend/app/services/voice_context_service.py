from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.schemas.tenant_features import VoiceExperienceLimits
from app.schemas.voice_context import (
    VoiceContextFieldRequest,
    VoiceContextFieldResponse,
    VoiceContextSchemaCreateRequest,
    VoiceContextSchemaMetaUpdateRequest,
    VoiceContextSchemaResponse,
    VoiceContextSchemaSummaryResponse,
)
from app.services.integration_event_service import IntegrationEventService
from app.services.tenant_feature_service import TenantFeatureService, VOICE_EXPERIENCES
from app.services.voice_agent_service import VoiceAgentService


class VoiceContextNotFoundError(ValueError):
    pass


class VoiceContextValidationError(ValueError):
    pass


class VoiceContextConflictError(PermissionError):
    pass


class VoiceContextService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = TenantFeatureService(db)
        self.agent_service = VoiceAgentService(db)
        self.event_service = IntegrationEventService(db)

    def list_schemas(
        self, tenant_id: str, agent_config_id: str
    ) -> list[VoiceContextSchemaSummaryResponse]:
        self._require_feature_and_agent(tenant_id, agent_config_id)
        schemas = list(
            self.db.scalars(
                select(TenantVoiceContextSchema)
                .where(
                    TenantVoiceContextSchema.tenant_id == tenant_id,
                    TenantVoiceContextSchema.agent_config_id == agent_config_id,
                )
                .order_by(TenantVoiceContextSchema.schema_key, TenantVoiceContextSchema.version.desc())
            ).all()
        )
        grouped: dict[str, list[TenantVoiceContextSchema]] = {}
        for schema in schemas:
            grouped.setdefault(schema.schema_key, []).append(schema)
        selected = []
        for versions in grouped.values():
            selected.append(
                next((item for item in versions if item.status == "active"), None)
                or next((item for item in versions if item.status == "draft"), None)
                or versions[0]
            )
        return [self.summary_response(schema) for schema in selected]

    def list_versions(
        self, tenant_id: str, agent_config_id: str, schema_key: str
    ) -> list[VoiceContextSchemaSummaryResponse]:
        self._require_feature_and_agent(tenant_id, agent_config_id)
        schemas = self.db.scalars(
            select(TenantVoiceContextSchema)
            .where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.agent_config_id == agent_config_id,
                TenantVoiceContextSchema.schema_key == schema_key,
            )
            .order_by(TenantVoiceContextSchema.version.desc())
        ).all()
        return [self.summary_response(schema) for schema in schemas]

    def get_schema(self, tenant_id: str, schema_id: str) -> TenantVoiceContextSchema:
        self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        schema = self.db.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
        )
        if schema is None:
            raise VoiceContextNotFoundError("Voice context schema not found.")
        self._require_agent(tenant_id, schema.agent_config_id)
        return schema

    def create_schema(
        self,
        tenant_id: str,
        agent_config_id: str,
        body: VoiceContextSchemaCreateRequest,
        user_id: str | None,
    ) -> TenantVoiceContextSchema:
        grant, agent = self._require_feature_and_agent(tenant_id, agent_config_id)
        existing = self.db.scalar(
            select(TenantVoiceContextSchema.id).where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.agent_config_id == agent_config_id,
                TenantVoiceContextSchema.schema_key == body.schema_key,
            )
        )
        if existing:
            raise VoiceContextValidationError("Schema key already exists for this voice agent.")
        self._ensure_experience_capacity(tenant_id, self._limits(grant))
        schema = TenantVoiceContextSchema(
            tenant_id=tenant_id,
            agent_config_id=agent_config_id,
            schema_key=body.schema_key,
            version=1,
            status="draft",
            name=body.name,
            description=body.description,
            created_by_user_id=user_id,
        )
        self.db.add(schema)
        self.db.flush()
        self._record_event(schema, agent.provider, "context_schema_created")
        self.db.refresh(schema)
        return schema

    def update_schema_meta(
        self,
        tenant_id: str,
        schema_id: str,
        body: VoiceContextSchemaMetaUpdateRequest,
    ) -> TenantVoiceContextSchema:
        schema = self._require_draft(tenant_id, schema_id)
        schema.name = body.name
        schema.description = body.description
        self.db.commit()
        self.db.refresh(schema)
        return schema

    def add_field(
        self,
        tenant_id: str,
        schema_id: str,
        body: VoiceContextFieldRequest,
    ) -> TenantVoiceContextField:
        schema = self._require_draft(tenant_id, schema_id)
        grant = self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        field_count = self.db.scalar(
            select(func.count(TenantVoiceContextField.id)).where(
                TenantVoiceContextField.schema_id == schema.id
            )
        ) or 0
        if field_count >= self._limits(grant).max_context_fields:
            raise VoiceContextValidationError("Maximum context fields limit reached.")
        field = TenantVoiceContextField(
            tenant_id=tenant_id,
            schema_id=schema.id,
            **body.model_dump(),
        )
        self.db.add(field)
        self._commit_field(field)
        return field

    def update_field(
        self,
        tenant_id: str,
        schema_id: str,
        field_id: str,
        body: VoiceContextFieldRequest,
    ) -> TenantVoiceContextField:
        schema = self._require_draft(tenant_id, schema_id)
        field = self.db.scalar(
            select(TenantVoiceContextField).where(
                TenantVoiceContextField.id == field_id,
                TenantVoiceContextField.schema_id == schema.id,
                TenantVoiceContextField.tenant_id == tenant_id,
            )
        )
        if field is None:
            raise VoiceContextNotFoundError("Voice context field not found.")
        for key, value in body.model_dump().items():
            setattr(field, key, value)
        self._commit_field(field)
        return field

    def delete_field(self, tenant_id: str, schema_id: str, field_id: str) -> None:
        schema = self._require_draft(tenant_id, schema_id)
        field = self.db.scalar(
            select(TenantVoiceContextField).where(
                TenantVoiceContextField.id == field_id,
                TenantVoiceContextField.schema_id == schema.id,
                TenantVoiceContextField.tenant_id == tenant_id,
            )
        )
        if field is None:
            raise VoiceContextNotFoundError("Voice context field not found.")
        self.db.delete(field)
        self.db.commit()

    def activate_schema(
        self, tenant_id: str, schema_id: str, user_id: str | None
    ) -> TenantVoiceContextSchema:
        schema = self._locked_schema(tenant_id, schema_id)
        self._ensure_draft(schema)
        if not schema.fields:
            raise VoiceContextValidationError("A schema must have at least one field before activation.")
        agent = self._require_agent(tenant_id, schema.agent_config_id)
        now = datetime.now(timezone.utc)
        active_schemas = self.db.scalars(
            select(TenantVoiceContextSchema)
            .where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.agent_config_id == schema.agent_config_id,
                TenantVoiceContextSchema.schema_key == schema.schema_key,
                TenantVoiceContextSchema.status == "active",
                TenantVoiceContextSchema.id != schema.id,
            )
            .with_for_update()
        ).all()
        for active in active_schemas:
            active.status = "archived"
            active.archived_at = now
        schema.status = "active"
        schema.activated_at = now
        schema.archived_at = None
        self._record_event(schema, agent.provider, "context_schema_activated", user_id)
        self.db.refresh(schema)
        return schema

    def archive_schema(
        self, tenant_id: str, schema_id: str, user_id: str | None
    ) -> TenantVoiceContextSchema:
        schema = self.get_schema(tenant_id, schema_id)
        if schema.status == "archived":
            raise VoiceContextConflictError("Archived schemas are immutable.")
        agent = self._require_agent(tenant_id, schema.agent_config_id)
        schema.status = "archived"
        schema.archived_at = datetime.now(timezone.utc)
        self._record_event(schema, agent.provider, "context_schema_archived", user_id)
        self.db.refresh(schema)
        return schema

    def fork_new_version(
        self, tenant_id: str, schema_id: str, user_id: str | None
    ) -> TenantVoiceContextSchema:
        source = self.get_schema(tenant_id, schema_id)
        if source.status == "draft":
            raise VoiceContextConflictError("Draft schemas must be edited directly.")
        grant, agent = self._require_feature_and_agent(tenant_id, source.agent_config_id)
        consumes_new_lineage = not self.db.scalar(
            select(TenantVoiceContextSchema.id).where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.agent_config_id == source.agent_config_id,
                TenantVoiceContextSchema.schema_key == source.schema_key,
                TenantVoiceContextSchema.status != "archived",
            )
        )
        if consumes_new_lineage:
            self._ensure_experience_capacity(tenant_id, self._limits(grant))
        next_version = (self.db.scalar(
            select(func.max(TenantVoiceContextSchema.version)).where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.agent_config_id == source.agent_config_id,
                TenantVoiceContextSchema.schema_key == source.schema_key,
            )
        ) or 0) + 1
        schema = TenantVoiceContextSchema(
            tenant_id=tenant_id,
            agent_config_id=source.agent_config_id,
            schema_key=source.schema_key,
            version=next_version,
            status="draft",
            name=source.name,
            description=source.description,
            created_by_user_id=user_id,
        )
        schema.fields = [
            TenantVoiceContextField(
                tenant_id=tenant_id,
                key=field.key,
                label=field.label,
                field_type=field.field_type,
                collection_mode=field.collection_mode,
                required=field.required,
                position=field.position,
                sensitivity=field.sensitivity,
                validation_json=dict(field.validation_json),
                options_json=list(field.options_json),
            )
            for field in source.fields
        ]
        self.db.add(schema)
        self.db.flush()
        self._record_event(schema, agent.provider, "context_schema_created")
        self.db.refresh(schema)
        return schema

    @staticmethod
    def field_response(field: TenantVoiceContextField) -> VoiceContextFieldResponse:
        return VoiceContextFieldResponse(
            id=field.id,
            key=field.key,
            label=field.label,
            field_type=field.field_type,
            collection_mode=field.collection_mode,
            required=field.required,
            position=field.position,
            sensitivity=field.sensitivity,
            validation_json=field.validation_json,
            options_json=field.options_json,
        )

    def schema_response(self, schema: TenantVoiceContextSchema) -> VoiceContextSchemaResponse:
        return VoiceContextSchemaResponse(
            id=schema.id,
            agent_config_id=schema.agent_config_id,
            schema_key=schema.schema_key,
            version=schema.version,
            status=schema.status,
            name=schema.name,
            description=schema.description,
            fields=[self.field_response(field) for field in schema.fields],
            created_at=schema.created_at,
            updated_at=schema.updated_at,
            activated_at=schema.activated_at,
            archived_at=schema.archived_at,
        )

    @staticmethod
    def summary_response(schema: TenantVoiceContextSchema) -> VoiceContextSchemaSummaryResponse:
        return VoiceContextSchemaSummaryResponse(
            id=schema.id,
            agent_config_id=schema.agent_config_id,
            schema_key=schema.schema_key,
            version=schema.version,
            status=schema.status,
            name=schema.name,
            field_count=len(schema.fields),
            updated_at=schema.updated_at,
        )

    def _require_feature_and_agent(self, tenant_id: str, agent_config_id: str):
        grant = self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        agent = self._require_agent(tenant_id, agent_config_id)
        return grant, agent

    def _require_agent(self, tenant_id: str, agent_config_id: str):
        try:
            return self.agent_service.validate_agent_belongs_to_tenant(
                tenant_id, agent_config_id
            )
        except ValueError as exc:
            raise VoiceContextNotFoundError(str(exc)) from exc

    def _require_draft(self, tenant_id: str, schema_id: str) -> TenantVoiceContextSchema:
        schema = self.get_schema(tenant_id, schema_id)
        self._ensure_draft(schema)
        return schema

    @staticmethod
    def _ensure_draft(schema: TenantVoiceContextSchema) -> None:
        if schema.status != "draft":
            raise VoiceContextConflictError(f"{schema.status.title()} schemas are immutable.")

    def _locked_schema(self, tenant_id: str, schema_id: str) -> TenantVoiceContextSchema:
        self.feature_service.require_enabled(tenant_id, VOICE_EXPERIENCES)
        schema = self.db.scalar(
            select(TenantVoiceContextSchema)
            .where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if schema is None:
            raise VoiceContextNotFoundError("Voice context schema not found.")
        self._require_agent(tenant_id, schema.agent_config_id)
        return schema

    def _ensure_experience_capacity(self, tenant_id: str, limits: VoiceExperienceLimits) -> None:
        lineages = self.db.execute(
            select(
                TenantVoiceContextSchema.agent_config_id,
                TenantVoiceContextSchema.schema_key,
            )
            .where(
                TenantVoiceContextSchema.tenant_id == tenant_id,
                TenantVoiceContextSchema.status != "archived",
            )
            .distinct()
        ).all()
        if len(lineages) >= limits.max_experiences:
            raise VoiceContextValidationError("Maximum voice experiences limit reached.")

    @staticmethod
    def _limits(grant) -> VoiceExperienceLimits:
        return VoiceExperienceLimits.model_validate(grant.limits_json)

    def _commit_field(self, field: TenantVoiceContextField) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise VoiceContextValidationError("Field key already exists in this schema.") from exc
        self.db.refresh(field)

    def _record_event(
        self,
        schema: TenantVoiceContextSchema,
        provider: str,
        event_type: str,
        user_id: str | None = None,
    ) -> None:
        self.event_service.record_event(
            tenant_id=schema.tenant_id,
            provider=provider,
            event_type=event_type,
            status="success",
            resource_type="voice_context_schema",
            resource_id=schema.id,
            metadata={
                "schema_key": schema.schema_key,
                "version": schema.version,
                "actor_user_id": user_id,
            },
        )
