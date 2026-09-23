from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.tool_registry import ToolRegistryValidationError
from app.domain.voice_registry import (
    VoiceRegistryValidationError,
    validate_model_settings,
    validate_runtime_selection,
)
from app.domain.resolved_tool import ResolvedToolDefinition
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
from app.services.tenant_tool_credential_service import TenantToolCredentialService
from app.services.tool_catalog_service import ToolCatalogService
from app.services.tool_resolver_service import ToolResolverService
from app.services.voice_selection_service import VoiceSelectionError, VoiceSelectionService

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
        elif management_mode == "serviglobal_managed":
            self._publish_voice_preflight(tenant_id, draft, realtime)
            self._publish_tools_preflight(tenant_id, draft)
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

    def tool_catalog(self, tenant_id: str) -> list[dict[str, Any]]:
        """The unified platform + tenant Custom Tools catalog, annotated
        per-tenant with whether each tool is actually usable -- drives the
        Agent Builder's "Herramientas" tab (checkbox + "Requiere configurar
        X" banner) and lets a tenant see the full catalog, including
        status="planned" platform entries, without exposing them as
        bindable."""
        self.feature_service.require_enabled(tenant_id, AGENT_BUILDER)
        return ToolCatalogService(self.db).build_catalog(
            tenant_id, is_available=lambda resolved: self._resolved_tool_available(tenant_id, resolved)
        )

    def _resolved_tool_available(self, tenant_id: str, resolved: ResolvedToolDefinition) -> bool:
        if resolved.source == "platform":
            return self._tool_integration_configured(tenant_id, resolved.required_integration)
        assert resolved.custom_tool_id is not None
        return TenantToolCredentialService(self.db).is_configured_or_not_required(
            tenant_id, resolved.custom_tool_id
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
        if body.settings:
            if body.management_mode == "provider_managed":
                raise AgentValidationError("settings is not configurable for provider_managed agents.")
            try:
                validate_model_settings(body.provider, body.model, body.settings)
            except VoiceRegistryValidationError as exc:
                raise AgentValidationError(str(exc)) from exc
            realtime["settings"] = body.settings
        if body.voice is not None:
            if body.management_mode == "provider_managed":
                raise AgentValidationError("voice is not configurable for provider_managed agents.")
            try:
                VoiceSelectionService().validate(body.provider, body.model, body.voice)
            except VoiceSelectionError as exc:
                raise AgentValidationError(str(exc)) from exc
            realtime["voice"] = body.voice.model_dump()
        if body.provider_overrides is not None:
            realtime["provider_overrides"] = body.provider_overrides.model_dump(exclude_none=True)
        if body.tools:
            if body.management_mode == "provider_managed":
                raise AgentValidationError("tools is not configurable for provider_managed agents.")
            try:
                self._validate_tool_bindings_for_tenant(tenant_id, body.tools)
            except ToolRegistryValidationError as exc:
                raise AgentValidationError(str(exc)) from exc
            binding["tools"] = [tool.model_dump() for tool in body.tools]
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

    def _publish_voice_preflight(
        self, tenant_id: str, draft: TenantAgentVersion, realtime: dict
    ) -> None:
        """Cheap, blocking publish-time checks for a serviglobal_managed
        voice -- never generates audio and never calls provider_managed's
        provider-agent preflight (that stays in its own branch in publish()).

        provider  -> confirm the Ultravox voice is still accessible
                     (metadata GET only, no TTS credit spent).
        provider_external -> confirm the tenant's Ultravox account has the
                     external provider's BYOK key configured, via
                     /accounts/me/tts_api_keys. Never calls voice_preview:
                     that would generate audio just to publish.

        If `realtime.voice` isn't set but the agent still has a legacy
        TenantVoiceAgentConfig.default_voice link, that's synthesized into
        the same provider-voice shape AgentCompilerService.compile() already
        uses, so legacy agents get the same accessibility check without any
        data migration.
        """
        voice = realtime.get("voice")
        if not voice and draft.voice_agent_config and draft.voice_agent_config.default_voice:
            voice = {
                "mode": "provider", "provider": "ultravox",
                "voice_id": draft.voice_agent_config.default_voice, "settings": {},
            }
        if not isinstance(voice, dict) or not voice:
            return
        voice_mode = voice.get("mode")
        if voice_mode not in ("provider", "provider_external"):
            raise AgentValidationError("voice_provider_not_supported")

        from app.services.ultravox_admin_service import UltravoxAdminService
        from app.services.ultravox_provider_client import UltravoxProviderError

        admin = UltravoxAdminService(self.db)
        try:
            if voice_mode == "provider":
                admin.get_voice(tenant_id, str(voice.get("voice_id") or ""))
            else:
                admin.validate_external_voice_credentials(tenant_id, str(voice.get("provider") or ""))
        except UltravoxProviderError as exc:
            code = "voice_not_accessible" if exc.code == "provider_resource_not_found" else exc.code
            raise AgentValidationError(code) from exc
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc

    def _validate_tool_bindings_for_tenant(self, tenant_id: str, bindings: list[Any]) -> None:
        """Draft-save-time shape/existence check for tool bindings, tenant-
        and resolver-aware (unlike app.domain.tool_registry.validate_tool_
        bindings, which only ever knows the static platform Registry).
        custom.* keys can only be validated with a DB lookup -- this is why
        a resolver-based check replaces the pure-registry one here, not just
        at publish time. Duplicate-key / not-found / not-available all
        raise the exact same ToolRegistryValidationError codes the platform
        registry's own validator used, so existing error-code handling
        (frontend + tests) is unaffected for platform tools.
        """
        resolver = ToolResolverService(self.db)
        seen: set[str] = set()
        for binding in bindings:
            key = binding.key
            if key in seen:
                raise ToolRegistryValidationError(f"Duplicate tool binding '{key}'.")
            seen.add(key)
            resolved = resolver.resolve(tenant_id, key)
            if resolved is None:
                raise ToolRegistryValidationError(f"tool_not_found:{key}")
            if resolved.status != "available":
                raise ToolRegistryValidationError(f"tool_not_available:{key}")

    def _publish_tools_preflight(self, tenant_id: str, draft: TenantAgentVersion) -> None:
        """Cheap, blocking publish-time checks for a serviglobal_managed
        agent's bound tools -- never executes a tool.

        For each `enabled` binding: re-confirms it is still a known,
        available tool (platform or tenant custom -- resolved through
        ToolResolverService, the same seam AgentCompilerService and
        ToolDispatchService use) and that the tenant actually has it
        configured (required_integration for platform tools, an active
        credential for custom ones when auth_type != none). Reuses each
        service's own tenant-scoped config resolution -- the same one the
        real tool execution path uses -- so this can never approve a tool
        the runtime would later fail to run.
        """
        bindings = draft.runtime_binding_json.get("tools", [])
        resolver = ToolResolverService(self.db)
        for binding in bindings:
            if not binding.get("enabled", True):
                continue
            key = str(binding.get("key") or "")
            resolved = resolver.resolve(tenant_id, key)
            if resolved is None:
                raise AgentValidationError(f"tool_not_found:{key}")
            if resolved.status != "available":
                raise AgentValidationError(f"tool_not_available:{key}")
            if not self._resolved_tool_available(tenant_id, resolved):
                raise AgentValidationError("tool_integration_not_configured")

    def _tool_integration_configured(self, tenant_id: str, required_integration: str | None) -> bool:
        """Cheap, tenant-scoped check reusing each integration's own real
        config resolution -- the same call the tool's actual execution path
        (Phase E) will make, so this can never say "available" for an
        integration that would then fail to resolve at call time."""
        if required_integration == "booking":
            from app.services.booking_service import BookingService

            try:
                BookingService(self.db)._effective_config(tenant_id)
                return True
            except ValueError:
                return False
        if required_integration == "whatsapp":
            from app.services.whatsapp_config_service import WhatsAppConfigService

            try:
                WhatsAppConfigService(self.db).get_active_client_config(tenant_id)
                return True
            except ValueError:
                return False
        if required_integration == "crm":
            # CRM is a first-party, always-on capability -- CrmContactService
            # / CrmLeadService operate on the tenant's own DB-native CRM
            # tables and require no external per-tenant integration to
            # configure, unlike booking/whatsapp. crm.create_lead must never
            # be reported unavailable for lack of something that doesn't
            # exist to configure.
            return True
        return required_integration is None

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
