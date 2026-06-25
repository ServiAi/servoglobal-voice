from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.crm import CrmLead, CrmPipelineStage

DEFAULT_STAGES = [
    {"key": "new", "name": "Nuevo", "position": 1, "is_default": True, "is_terminal": False},
    {"key": "contacted", "name": "Contactado", "position": 2, "is_default": False, "is_terminal": False},
    {"key": "connected", "name": "Conectado", "position": 3, "is_default": False, "is_terminal": False},
    {"key": "qualified", "name": "Calificado", "position": 4, "is_default": False, "is_terminal": False},
    {"key": "scheduled", "name": "Agendado", "position": 5, "is_default": False, "is_terminal": False},
    {"key": "voicemail", "name": "Buzón de voz", "position": 6, "is_default": False, "is_terminal": False},
    {"key": "follow_up", "name": "En seguimiento", "position": 7, "is_default": False, "is_terminal": False},
    {"key": "not_interested", "name": "No interesado", "position": 8, "is_default": False, "is_terminal": True},
    {"key": "won", "name": "Ganado", "position": 9, "is_default": False, "is_terminal": True},
    {"key": "lost", "name": "Perdido", "position": 10, "is_default": False, "is_terminal": True},
]

DEFAULT_STAGE_KEYS = {stage["key"] for stage in DEFAULT_STAGES}

class CrmPipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_default_pipeline(self, tenant_id: str) -> list[CrmPipelineStage]:
        stages = list(
            self.db.scalars(
                select(CrmPipelineStage)
                .where(CrmPipelineStage.tenant_id == tenant_id)
                .order_by(CrmPipelineStage.position.asc())
            ).all()
        )

        stages_by_key = {stage.key: stage for stage in stages}
        for stage_data in DEFAULT_STAGES:
            stage = stages_by_key.get(stage_data["key"])
            if stage is None:
                stage = CrmPipelineStage(
                    tenant_id=tenant_id,
                    key=stage_data["key"],
                    name=stage_data["name"],
                    position=stage_data["position"],
                    is_default=stage_data["is_default"],
                    is_terminal=stage_data["is_terminal"],
                )
                self.db.add(stage)
                stages_by_key[stage.key] = stage
            else:
                stage.name = stage_data["name"]
                stage.position = stage_data["position"]
                stage.is_default = stage_data["is_default"]
                stage.is_terminal = stage_data["is_terminal"]

        self.db.flush()
        follow_up_stage = stages_by_key["follow_up"]
        for stage in stages:
            if stage.key in DEFAULT_STAGE_KEYS:
                continue
            leads = self.db.scalars(
                select(CrmLead).where(CrmLead.current_stage_id == stage.id)
            ).all()
            for lead in leads:
                lead.current_stage_id = follow_up_stage.id

        self.db.commit()
        return list(
            self.db.scalars(
                select(CrmPipelineStage)
                .where(
                    CrmPipelineStage.tenant_id == tenant_id,
                    CrmPipelineStage.key.in_(DEFAULT_STAGE_KEYS),
                )
                .order_by(CrmPipelineStage.position.asc())
            ).all()
        )

    def get_stage_by_key(self, tenant_id: str, key: str) -> CrmPipelineStage:
        if key not in DEFAULT_STAGE_KEYS:
            key = "follow_up"
        self.ensure_default_pipeline(tenant_id)

        stage = self.db.scalar(
            select(CrmPipelineStage).where(
                CrmPipelineStage.tenant_id == tenant_id,
                CrmPipelineStage.key == key,
            )
        )
        if stage is not None:
            return stage

        # Trigger lazy creation of pipeline stages
        stages = self.ensure_default_pipeline(tenant_id)
        
        # Try finding the stage again
        for s in stages:
            if s.key == key:
                return s

        # Fallback to the default stage
        for s in stages:
            if s.is_default:
                return s

        return stages[0]
