from sqlalchemy import select

from app.modules.voice_experiences.infrastructure.experience_models import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)


class SqlAlchemyAgentReferenceReader:
    def __init__(self, session: object) -> None:
        self.session = session

    def is_agent_referenced(self, tenant_id: str, agent_id: str) -> bool:
        for model in (TenantVoiceExperience, TenantVoiceExperienceVersion):
            found = self.session.scalar(
                select(model.id)
                .where(model.tenant_id == tenant_id, model.agent_id == agent_id)
                .limit(1)
            )
            if found is not None:
                return True
        return False
