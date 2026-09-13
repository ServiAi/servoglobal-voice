from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.voice_registry import VoiceRegistryValidationError, validate_runtime_selection
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.integrations import TenantVoiceAgentConfig
from app.schemas.agents import (
    AgentBehavior,
    AgentCreateRequest,
    AgentDraftUpdateRequest,
    AgentIdentity,
    AgentInstructions,
    AgentResponse,
    AgentUpdateRequest,
    AgentVersionResponse,
)
from app.services.integration_event_service import IntegrationEventService
from app.services.tenant_feature_service import AGENT_BUILDER, TenantFeatureService

VERSION_CONSTRAINT = "uq_tenant_agent_versions_agent_version"


class AgentNotFoundError(ValueError):
    pass


class AgentConflictError(ValueError):
    pass


class AgentValidationError(ValueError):
    pass


def _matches_constraint(exc: IntegrityError, name: str, sqlite_columns: str) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == name:
        return True
    message = str(exc.orig)
    return name in message or f"UNIQUE constraint failed: {sqlite_columns}" in message


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = TenantFeatureService(db)
        self.event_service = IntegrationEventService(db)

    def list_agents(self, tenant_id: str) -> list[TenantAgent]:
        self.feature_service.require_enabled(tenant_id, AGENT_BUILDER)
        return list(
            self.db.scalars(
                select(TenantAgent)
                .where(TenantAgent.tenant_id == tenant_id)
                .order_by(TenantAgent.created_at.desc())
            ).all()
        )

    def get_agent(self, tenant_id: str, agent_id: str) -> TenantAgent:
        self.feature_service.require_enabled(tenant_id, AGENT_BUILDER)
        agent = self.db.scalar(
            select(TenantAgent).where(
                TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id
            )
        )
        if agent is None:
            raise AgentNotFoundError("Agent not found.")
        return agent

    def create_agent(
        self, tenant_id: str, body: AgentCreateRequest, user_id: str | None
    ) -> TenantAgent:
        self.feature_service.require_enabled(tenant_id, AGENT_BUILDER)
        self._validate_voice_agent_config(tenant_id, body.voice_agent_config_id)
        agent = TenantAgent(
            tenant_id=tenant_id,
            name=body.name,
            description=body.description,
            status="draft",
            created_by_user_id=user_id,
        )
        self.db.add(agent)
        self.db.flush()
        version = TenantAgentVersion(
            agent_id=agent.id,
            tenant_id=tenant_id,
            version=1,
            status="draft",
            language=body.language,
            timezone=body.timezone,
            identity_json=AgentIdentity(
                name=body.name, description=body.description
            ).model_dump(),
            instructions_json=body.instructions.model_dump(),
            behavior_json=body.behavior.model_dump(),
            runtime_binding_json=self._build_runtime_binding_for_tenant(tenant_id, body),
            voice_agent_config_id=body.voice_agent_config_id,
            created_by_user_id=user_id,
        )
        self.db.add(version)
        self.db.flush()
        agent.draft_version_id = version.id
        self.db.commit()
        self._record_event(agent, "agent_created", user_id, {"version": 1})
        self.db.refresh(agent)
        return agent

    def update_agent(
        self, tenant_id: str, agent_id: str, body: AgentUpdateRequest
    ) -> TenantAgent:
        agent = self.get_agent(tenant_id, agent_id)
        self._ensure_mutable(agent)
        agent.name = body.name
        agent.description = body.description
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def get_draft(self, tenant_id: str, agent_id: str) -> TenantAgentVersion:
        agent = self.get_agent(tenant_id, agent_id)
        if agent.draft_version_id is None:
            raise AgentConflictError(
                "Agent has no editable draft. Create a new draft first."
            )
        return self._get_version(tenant_id, agent.draft_version_id)

    def update_draft(
        self, tenant_id: str, agent_id: str, body: AgentDraftUpdateRequest
    ) -> TenantAgentVersion:
        # Single transaction for TenantAgent identity + TenantAgentVersion
        # draft content: the frontend used to PATCH these as two independent
        # requests, which could leave agent.name/description out of sync
        # with version.identity_json if one request failed after the other
        # succeeded.
        agent = self._locked_agent(tenant_id, agent_id)
        self._ensure_mutable(agent)
        if agent.draft_version_id is None:
            raise AgentConflictError(
                "Agent has no editable draft. Create a new draft first."
            )
        self._validate_voice_agent_config(tenant_id, body.voice_agent_config_id)
        version = self._get_version(tenant_id, agent.draft_version_id)
        agent.name = body.name
        agent.description = body.description
        version.language = body.language
        version.timezone = body.timezone
        version.identity_json = AgentIdentity(
            name=agent.name, description=agent.description
        ).model_dump()
        version.instructions_json = body.instructions.model_dump()
        version.behavior_json = body.behavior.model_dump()
        version.runtime_binding_json = self._build_runtime_binding_for_tenant(tenant_id, body)
        version.voice_agent_config_id = body.voice_agent_config_id
        self.db.commit()
        self._record_event(agent, "agent_draft_updated", None, {"version": version.version})
        self.db.refresh(version)
        return version

    def create_next_draft(
        self, tenant_id: str, agent_id: str, user_id: str | None
    ) -> TenantAgentVersion:
        agent = self._locked_agent(tenant_id, agent_id)
        self._ensure_mutable(agent)
        if agent.draft_version_id is not None:
            raise AgentConflictError("Agent already has an editable draft.")
        if agent.published_version_id is None:
            raise AgentConflictError("Agent has no published version to branch from.")
        draft = self._new_draft_from_published(agent, user_id)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _matches_constraint(
                exc, VERSION_CONSTRAINT, "tenant_agent_versions.agent_id, tenant_agent_versions.version"
            ):
                raise AgentConflictError("A concurrent draft already won.") from exc
            raise
        self.db.refresh(draft)
        return draft

    def _new_draft_from_published(
        self, agent: TenantAgent, user_id: str | None
    ) -> TenantAgentVersion:
        published = self._get_version(agent.tenant_id, agent.published_version_id)
        next_version_number = (
            self.db.scalar(
                select(func.max(TenantAgentVersion.version)).where(
                    TenantAgentVersion.agent_id == agent.id
                )
            )
            or 0
        ) + 1
        draft = TenantAgentVersion(
            agent_id=agent.id,
            tenant_id=agent.tenant_id,
            version=next_version_number,
            status="draft",
            language=published.language,
            timezone=published.timezone,
            identity_json=deepcopy(published.identity_json),
            instructions_json=deepcopy(published.instructions_json),
            behavior_json=deepcopy(published.behavior_json),
            runtime_binding_json=deepcopy(published.runtime_binding_json),
            voice_agent_config_id=published.voice_agent_config_id,
            created_by_user_id=user_id,
        )
        self.db.add(draft)
        self.db.flush()
        agent.draft_version_id = draft.id
        return draft

    def publish(
        self,
        tenant_id: str,
        agent_id: str,
        user_id: str | None,
        expected_draft_version_id: str | None = None,
    ) -> TenantAgent:
        agent = self._locked_agent(tenant_id, agent_id)
        self._ensure_mutable(agent)
        if agent.draft_version_id is None:
            raise AgentConflictError("Agent has no draft to publish.")
        if (
            expected_draft_version_id is not None
            and expected_draft_version_id != agent.draft_version_id
        ):
            # The draft was saved and/or published by someone else (another
            # tab, another admin) between the caller reading it and this
            # publish call. Refuse rather than publish a version the caller
            # never saw.
            raise AgentConflictError(
                "Draft has changed since it was last saved. Reload and try again."
            )
        draft = self._get_version(tenant_id, agent.draft_version_id)
        realtime = draft.runtime_binding_json.get("realtime", {})
        management_mode = realtime.get("management_mode", "serviglobal_managed")
        if management_mode == "serviglobal_managed" and not draft.instructions_json.get("system_prompt", "").strip():
            raise AgentValidationError("system_prompt is required before publishing.")
        if management_mode == "provider_managed":
            provider_agent = realtime.get("provider_agent") or {}
            try:
                from app.services.ultravox_admin_service import UltravoxAdminService
                from app.services.ultravox_provider_client import UltravoxProviderError

                UltravoxAdminService(self.db).validate_execution_preflight(
                    tenant_id, str(provider_agent.get("agent_id") or "")
                )
            except (ValueError, UltravoxProviderError) as exc:
                raise AgentValidationError(str(exc)) from exc
        previous_published_id = agent.published_version_id
        now = datetime.now(timezone.utc)
        draft.status = "published"
        draft.published_at = now
        if previous_published_id:
            previous = self._get_version(tenant_id, previous_published_id)
            previous.status = "superseded"
        agent.published_version_id = draft.id
        agent.draft_version_id = None
        agent.status = "active"
        self.db.commit()
        self._record_event(agent, "agent_published", user_id, {"version": draft.version})
        self.db.refresh(agent)
        return agent

    def unpublish(
        self, tenant_id: str, agent_id: str, user_id: str | None
    ) -> TenantAgent:
        agent = self._locked_agent(tenant_id, agent_id)
        self._ensure_mutable(agent)
        if agent.published_version_id is None:
            raise AgentConflictError("Agent is not published.")
        published = self._get_version(tenant_id, agent.published_version_id)
        draft = (
            self._get_version(tenant_id, agent.draft_version_id)
            if agent.draft_version_id
            else self._new_draft_from_published(agent, user_id)
        )
        published.status = "superseded"
        agent.published_version_id = None
        agent.status = "draft"
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _matches_constraint(
                exc, VERSION_CONSTRAINT, "tenant_agent_versions.agent_id, tenant_agent_versions.version"
            ):
                raise AgentConflictError("A concurrent draft already won.") from exc
            raise
        self._record_event(
            agent,
            "agent_unpublished",
            user_id,
            {"version": published.version, "draft_version": draft.version},
        )
        self.db.refresh(agent)
        return agent

    def archive_agent(
        self, tenant_id: str, agent_id: str, user_id: str | None
    ) -> TenantAgent:
        agent = self._locked_agent(tenant_id, agent_id)
        if agent.status == "archived":
            raise AgentConflictError("Agent is already archived.")
        agent.status = "archived"
        agent.archived_at = datetime.now(timezone.utc)
        self.db.commit()
        self._record_event(agent, "agent_archived", user_id, {})
        self.db.refresh(agent)
        return agent

    async def delete_agent(self, tenant_id: str, agent_id: str, user_id: str | None) -> None:
        from app.models.voice_sessions import VoiceSession
        from app.services.livekit_runtime_backend import LiveKitRuntimeBackend
        from app.services.voice_session_service import VoiceSessionService

        agent = self._locked_agent(tenant_id, agent_id)
        if agent.status != "archived":
            raise AgentConflictError("agent_delete_requires_archived")
        sessions = list(self.db.scalars(select(VoiceSession).where(
            VoiceSession.tenant_id == tenant_id, VoiceSession.agent_id == agent.id
        ).with_for_update()).all())
        closer = LiveKitRuntimeBackend()
        for session in sessions:
            if session.status in {"ended", "failed", "cancelled"}:
                continue
            if session.status == "dispatching" and not session.livekit_room_name:
                raise AgentConflictError("agent_delete_session_dispatching")
            if session.status != "requested":
                if session.runtime_engine != "livekit" or session.livekit_room_name not in (None, f"sg-vs-{session.id}"):
                    raise AgentConflictError("agent_delete_session_unverified")
                try:
                    await closer.close_session_room(session.id)
                except Exception as exc:
                    raise AgentConflictError("agent_delete_room_close_failed") from exc
                self.db.refresh(session)
        voice_sessions = VoiceSessionService(self.db)
        for session in sessions:
            if session.status not in {"ended", "failed", "cancelled"}:
                session.end_reason = "agent_deleted"
                voice_sessions.transition(session, "cancelled", commit=False)
                voice_sessions.record_event(
                    session, "voice.session.cancelled", source="control-plane",
                    payload={"end_reason": session.end_reason}, commit=False,
                )
            session.deleted_agent_id = session.agent_id
            session.deleted_agent_version_id = session.agent_version_id
            session.agent_id = None
            session.agent_version_id = None
        resource_id = agent.id
        agent.published_version_id = None
        agent.draft_version_id = None
        self.db.flush()
        self.db.delete(agent)
        self.db.commit()
        self.event_service.record_event(
            tenant_id=agent.tenant_id,
            provider="agent_builder",
            event_type="agent_deleted",
            status="success",
            resource_type="agent",
            resource_id=resource_id,
            metadata={"actor_user_id": user_id, "status": "deleted"},
        )

    def list_versions(self, tenant_id: str, agent_id: str) -> list[TenantAgentVersion]:
        agent = self.get_agent(tenant_id, agent_id)
        return list(
            self.db.scalars(
                select(TenantAgentVersion)
                .where(
                    TenantAgentVersion.agent_id == agent.id,
                    TenantAgentVersion.tenant_id == tenant_id,
                )
                .order_by(TenantAgentVersion.version.desc())
            ).all()
        )

    # -- helpers --

    def _get_version(self, tenant_id: str, version_id: str) -> TenantAgentVersion:
        version = self.db.scalar(
            select(TenantAgentVersion).where(
                TenantAgentVersion.id == version_id,
                TenantAgentVersion.tenant_id == tenant_id,
            )
        )
        if version is None:
            raise AgentNotFoundError("Agent version not found.")
        return version

    def _locked_agent(self, tenant_id: str, agent_id: str) -> TenantAgent:
        self.feature_service.require_enabled(tenant_id, AGENT_BUILDER)
        agent = self.db.scalar(
            select(TenantAgent)
            .where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id)
            .with_for_update()
        )
        if agent is None:
            raise AgentNotFoundError("Agent not found.")
        return agent

    def _validate_voice_agent_config(
        self, tenant_id: str, voice_agent_config_id: str | None
    ) -> None:
        if voice_agent_config_id is None:
            return
        config = self.db.get(TenantVoiceAgentConfig, voice_agent_config_id)
        if config is None or config.tenant_id != tenant_id:
            raise AgentValidationError(
                "voice_agent_config_id does not exist or does not belong to this tenant."
            )

    @staticmethod
    def _build_runtime_binding(pipeline_type: str, provider: str, model: str) -> dict:
        try:
            validate_runtime_selection(pipeline_type, provider, model)
        except VoiceRegistryValidationError as exc:
            raise AgentValidationError(str(exc)) from exc
        return {
            "pipeline_type": pipeline_type,
            "realtime": {
                "provider": provider,
                "model": model,
                "management_mode": "serviglobal_managed",
            },
        }

    def _build_runtime_binding_for_tenant(self, tenant_id: str, body: Any) -> dict:
        binding = self._build_runtime_binding(body.pipeline_type, body.provider, body.model)
        realtime = binding["realtime"]
        realtime["management_mode"] = body.management_mode
        if body.voice is not None:
            realtime["voice"] = body.voice.model_dump()
        if body.provider_overrides is not None:
            realtime["provider_overrides"] = body.provider_overrides.model_dump(exclude_none=True)
        if body.management_mode == "provider_managed":
            if body.provider != "ultravox" or body.provider_agent is None:
                raise AgentValidationError("Unsupported provider-managed configuration.")
            from app.services.ultravox_admin_service import UltravoxAdminService

            remote = UltravoxAdminService(self.db).validate_provider_agent_link(
                tenant_id, body.provider_agent.agent_id
            )
            realtime["provider_agent"] = {
                "agent_id": remote.agent_id,
                "observed_published_revision_id": remote.published_revision_id,
            }
            realtime["provider_extensions"] = {
                "tools": [tool.model_dump() for tool in remote.tools],
                "has_unsupported_client_tools": remote.has_unsupported_client_tools,
            }
        return binding

    @staticmethod
    def _ensure_mutable(agent: TenantAgent) -> None:
        if agent.status == "archived":
            raise AgentConflictError("Archived agents are immutable.")

    def _record_event(
        self,
        agent: TenantAgent,
        event_type: str,
        user_id: str | None,
        extra_metadata: dict[str, Any],
    ) -> None:
        metadata = {"actor_user_id": user_id, "status": agent.status}
        metadata.update(extra_metadata)
        self.event_service.record_event(
            tenant_id=agent.tenant_id,
            provider="agent_builder",
            event_type=event_type,
            status="success",
            resource_type="agent",
            resource_id=agent.id,
            metadata=metadata,
        )

    @staticmethod
    def response(agent: TenantAgent) -> AgentResponse:
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            status=agent.status,
            published_version_id=agent.published_version_id,
            draft_version_id=agent.draft_version_id,
            archived_at=agent.archived_at,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )

    @staticmethod
    def version_response(version: TenantAgentVersion) -> AgentVersionResponse:
        return AgentVersionResponse(
            id=version.id,
            agent_id=version.agent_id,
            version=version.version,
            status=version.status,
            language=version.language,
            timezone=version.timezone,
            identity=AgentIdentity.model_validate(version.identity_json),
            instructions=AgentInstructions.model_validate(version.instructions_json),
            behavior=AgentBehavior.model_validate(version.behavior_json),
            runtime_binding=version.runtime_binding_json,
            voice_agent_config_id=version.voice_agent_config_id,
            published_at=version.published_at,
            created_at=version.created_at,
        )
