from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmActivity, CrmLead, CrmPipelineStage
from app.models.identity import _utcnow
from app.services.crm_pipeline_service import CrmPipelineService


TERMINAL_STAGES = {"not_interested", "won", "lost"}
AUTOMATIC_TRANSITIONS = {
    "new": {"contacted", "connected", "qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "contacted": {"connected", "qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "connected": {"qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "qualified": {"scheduled", "voicemail", "follow_up", "not_interested"},
    "voicemail": {"contacted", "connected", "qualified", "scheduled", "follow_up", "not_interested"},
    "follow_up": {"contacted", "connected", "qualified", "scheduled", "voicemail", "not_interested"},
    "scheduled": set(),
    "not_interested": set(),
    "won": set(),
    "lost": set(),
}


class CrmStageTransitionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.pipeline_service = CrmPipelineService(db)

    def move_to_contacted(self, tenant_id: str, lead: CrmLead, *, call_id: str | None = None) -> bool:
        return self.move(
            tenant_id,
            lead,
            "contacted",
            call_id=call_id,
            description="El lead avanzo automaticamente a 'Contactado' al iniciar el intento de llamada.",
        )

    def move_to_connected(self, tenant_id: str, lead: CrmLead, *, call_id: str | None = None) -> bool:
        return self.move(
            tenant_id,
            lead,
            "connected",
            call_id=call_id,
            description="El lead avanzo automaticamente a 'Conectado' al establecerse la llamada.",
        )

    def move_to_qualified(
        self,
        tenant_id: str,
        lead: CrmLead,
        *,
        call_id: str | None = None,
        description: str | None = None,
    ) -> bool:
        return self.move(
            tenant_id,
            lead,
            "qualified",
            call_id=call_id,
            description=description or "El lead avanzo a 'Calificado' por reglas deterministicas de interes comercial.",
        )

    def move_to_scheduled(self, tenant_id: str, lead: CrmLead, *, call_id: str | None = None) -> bool:
        return self.move(
            tenant_id,
            lead,
            "scheduled",
            call_id=call_id,
            description="El lead cambio a 'Agendado' porque se verifico un evento real de agenda.",
        )

    def move_to_follow_up(
        self,
        tenant_id: str,
        lead: CrmLead,
        *,
        call_id: str | None = None,
        description: str | None = None,
    ) -> bool:
        return self.move(
            tenant_id,
            lead,
            "follow_up",
            call_id=call_id,
            description=description or "El lead cambio a 'En seguimiento' porque requiere accion posterior.",
        )

    def move_to_voicemail(
        self,
        tenant_id: str,
        lead: CrmLead,
        *,
        call_id: str | None = None,
        description: str | None = None,
    ) -> bool:
        return self.move(
            tenant_id,
            lead,
            "voicemail",
            call_id=call_id,
            description=description or "El lead cambio a 'Buzon de voz' por resultado deterministico de la llamada.",
        )

    def move_to_not_interested(self, tenant_id: str, lead: CrmLead, *, call_id: str | None = None) -> bool:
        return self.move(
            tenant_id,
            lead,
            "not_interested",
            call_id=call_id,
            description="El lead cambio a 'No interesado' por rechazo explicito detectado.",
        )

    def move(
        self,
        tenant_id: str,
        lead: CrmLead,
        stage_key: str,
        *,
        call_id: str | None = None,
        description: str,
        manual: bool = False,
    ) -> bool:
        if not manual and stage_key in {"won", "lost"}:
            return False

        target_stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
        current_stage = self.db.get(CrmPipelineStage, lead.current_stage_id)
        current_key = current_stage.key if current_stage else None

        if not manual and current_key in TERMINAL_STAGES:
            return False

        if current_stage and current_stage.id == target_stage.id:
            self._create_stage_activity(
                tenant_id,
                lead,
                target_stage,
                call_id=call_id,
                description=description,
                from_stage_id=None,
            )
            return True

        if not manual and current_key:
            allowed = AUTOMATIC_TRANSITIONS.get(current_key, set())
            if target_stage.key not in allowed:
                return False

        previous_stage_id = lead.current_stage_id
        lead.current_stage_id = target_stage.id
        if target_stage.key == "won":
            lead.status = "won"
        elif target_stage.key in {"lost", "not_interested"}:
            lead.status = "lost"

        self.db.commit()
        self.db.refresh(lead)
        self._create_stage_activity(
            tenant_id,
            lead,
            target_stage,
            call_id=call_id,
            description=description,
            from_stage_id=previous_stage_id,
        )
        return True

    def _create_stage_activity(
        self,
        tenant_id: str,
        lead: CrmLead,
        target_stage: CrmPipelineStage,
        *,
        call_id: str | None,
        description: str,
        from_stage_id: str | None,
    ) -> CrmActivity:
        existing_activity = None
        if call_id:
            existing_activity = self.db.scalar(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.call_id == call_id,
                    CrmActivity.activity_type == "stage_changed",
                    CrmActivity.deduplication_key == target_stage.key,
                )
            )
        if existing_activity is not None:
            return existing_activity

        activity = CrmActivity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            call_id=call_id,
            activity_type="stage_changed",
            title=f"Etapa cambiada a {target_stage.name}",
            description=description,
            outcome=None,
            payload_json={},
            occurred_at=_utcnow(),
            from_stage_id=from_stage_id,
            to_stage_id=target_stage.id,
            deduplication_key=target_stage.key,
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity
