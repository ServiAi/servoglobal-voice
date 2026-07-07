from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.schemas.integrations import VoiceAgentConfigRequest, VoiceAgentConfigResponse
from app.services.integration_event_service import IntegrationEventService


class VoiceAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_service = IntegrationEventService(db)

    def list_agent_configs(self, tenant_id: str) -> list[TenantVoiceAgentConfig]:
        return list(
            self.db.scalars(
                select(TenantVoiceAgentConfig).where(
                    TenantVoiceAgentConfig.tenant_id == tenant_id
                )
            ).all()
        )

    def get_agent_config(self, tenant_id: str, agent_config_id: str) -> TenantVoiceAgentConfig | None:
        agent = self.db.get(TenantVoiceAgentConfig, agent_config_id)
        if agent and agent.tenant_id != tenant_id:
            return None
        return agent

    def validate_agent_belongs_to_tenant(self, tenant_id: str, agent_config_id: str) -> TenantVoiceAgentConfig:
        agent = self.get_agent_config(tenant_id, agent_config_id)
        if agent is None:
            raise ValueError("Voice agent config does not exist or does not belong to this tenant.")
        return agent

    def create_or_update_agent_config(
        self,
        tenant_id: str,
        body: VoiceAgentConfigRequest,
        agent_config_id: str | None = None,
    ) -> TenantVoiceAgentConfig:
        if body.provider_config_id:
            provider_config = self.db.get(TenantVoiceProviderConfig, body.provider_config_id)
            if not provider_config or provider_config.tenant_id != tenant_id:
                raise ValueError("Provider config does not exist or does not belong to this tenant.")

        if agent_config_id:
            agent = self.validate_agent_belongs_to_tenant(tenant_id, agent_config_id)
        else:
            agent = TenantVoiceAgentConfig(tenant_id=tenant_id)
            self.db.add(agent)

        agent.provider_config_id = body.provider_config_id
        agent.provider = body.provider
        agent.provider_agent_id = body.provider_agent_id
        agent.display_name = body.display_name
        agent.description = body.description
        agent.purpose = body.purpose
        agent.default_language = body.default_language
        agent.default_timezone = body.default_timezone
        agent.default_voice = body.default_voice
        agent.default_system_prompt = body.default_system_prompt
        agent.default_tools_json = body.default_tools_json
        agent.status = body.status

        self.db.commit()
        self.db.refresh(agent)

        self.event_service.record_event(
            tenant_id=tenant_id,
            provider=body.provider,
            event_type="agent_config_updated",
            status="success",
            resource_type="agent",
            resource_id=agent.id,
            metadata={"display_name": agent.display_name, "purpose": agent.purpose},
        )

        return agent

    def get_default_agent(self, tenant_id: str, provider: str = "ultravox") -> TenantVoiceAgentConfig | None:
        provider_config = self.db.scalar(
            select(TenantVoiceProviderConfig).where(
                TenantVoiceProviderConfig.tenant_id == tenant_id,
                TenantVoiceProviderConfig.provider == provider,
            )
        )
        if provider_config and provider_config.default_voice_agent_id:
            agent = self.db.scalar(
                select(TenantVoiceAgentConfig).where(
                    TenantVoiceAgentConfig.tenant_id == tenant_id,
                    TenantVoiceAgentConfig.provider_agent_id == provider_config.default_voice_agent_id,
                )
            )
            if agent:
                return agent

        return self.db.scalar(
            select(TenantVoiceAgentConfig).where(
                TenantVoiceAgentConfig.tenant_id == tenant_id,
                TenantVoiceAgentConfig.status == "active",
            ).limit(1)
        )

    def response(self, agent: TenantVoiceAgentConfig) -> VoiceAgentConfigResponse:
        return VoiceAgentConfigResponse(
            id=agent.id,
            provider=agent.provider,
            provider_agent_id=agent.provider_agent_id,
            display_name=agent.display_name,
            description=agent.description,
            purpose=agent.purpose,
            default_language=agent.default_language,
            default_timezone=agent.default_timezone,
            default_voice=agent.default_voice,
            status=agent.status,
        )
