from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity
from app.models.identity import _utcnow
from app.services.crm_contact_service import CrmContactService
from app.services.crm_lead_service import CrmLeadService
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_classifier_service import CrmClassifierService

logger = logging.getLogger(__name__)

class CrmIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.contact_service = CrmContactService(db)
        self.lead_service = CrmLeadService(db)
        self.pipeline_service = CrmPipelineService(db)
        self.classifier_service = CrmClassifierService()

    def process_ultravox_event(self, payload: dict[str, Any], call_record: Call) -> None:
        try:
            tenant_id = call_record.tenant_id
            if not tenant_id:
                logger.warning("CRM ingestion skipped: call record has no tenant_id")
                return

            event_type = self._event_type(payload)
            
            # Extract metadata and states
            metadata = self._get_metadata(payload)
            initial_state = self._get_initial_state(payload)
            
            # Resolve customer data
            phone = self.resolve_phone(payload, metadata, initial_state)
            email = self.resolve_email(metadata, initial_state)
            name = self.resolve_name(metadata, initial_state)
            
            # 1. Resolve or create contact
            contact = self.contact_service.get_or_create_contact(
                tenant_id=tenant_id,
                phone=phone,
                email=email,
                name=name,
                metadata=metadata,
            )
            
            # Build lead metadata dictionary
            lead_meta = {
                "interest": metadata.get("interest") or initial_state.get("interest"),
                "industry": metadata.get("industry") or initial_state.get("industry"),
                "use_case": metadata.get("use_case") or initial_state.get("use_case"),
                "volume": metadata.get("volume") or initial_state.get("volume"),
                "pain_point": metadata.get("pain_point") or initial_state.get("pain_point"),
                "budget_range": metadata.get("budget_range"),
                "intent_level": metadata.get("intent_level"),
                "source": metadata.get("source") or metadata.get("utm_source") or initial_state.get("source"),
                "campaign": metadata.get("campaign") or metadata.get("utm_campaign") or initial_state.get("campaign"),
            }
            
            # 2. Resolve or create lead
            lead = self.lead_service.get_or_create_open_lead(
                tenant_id=tenant_id,
                contact_id=contact.id,
                call_id=call_record.id,
                metadata=lead_meta,
            )
            
            # Handle specific events
            if event_type == "call.started":
                self._create_or_update_activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    activity_type="call_started",
                    title="Llamada iniciada",
                    description=f"Se inició un intento de llamada con el cliente ({contact.phone or 'sin teléfono'}).",
                    outcome=None,
                    payload_json=payload,
                )
                
            elif event_type == "call.joined":
                # Move lead to connected stage
                connected_stage = self.pipeline_service.get_stage_by_key(tenant_id, "connected")
                
                previous_stage_id = lead.current_stage_id
                if previous_stage_id != connected_stage.id:
                    lead.current_stage_id = connected_stage.id
                    self.db.commit()
                    # Create stage changed activity
                    self._create_or_update_activity(
                        tenant_id=tenant_id,
                        lead_id=lead.id,
                        contact_id=contact.id,
                        call_id=call_record.id,
                        activity_type="stage_changed",
                        title=f"Etapa cambiada a {connected_stage.name}",
                        description=f"El lead avanzó automáticamente a '{connected_stage.name}' al establecerse la llamada.",
                        outcome=None,
                        payload_json={},
                        from_stage_id=previous_stage_id,
                        to_stage_id=connected_stage.id,
                        deduplication_key=connected_stage.key,
                    )

                self._create_or_update_activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    activity_type="call_joined",
                    title="Llamada establecida",
                    description="El cliente se conectó a la llamada exitosamente.",
                    outcome="connected",
                    payload_json=payload,
                )
                
            elif event_type == "call.ended":
                # Update summaries from call record or payload
                call_obj = payload.get("call") or {}
                summary = call_obj.get("summary") or call_record.summary
                short_summary = call_obj.get("shortSummary") or call_obj.get("short_summary") or call_record.short_summary
                
                if summary:
                    lead.summary = summary
                if short_summary:
                    lead.short_summary = short_summary
                lead.last_call_id = call_record.id
                self.db.commit()
                
                # Classify lead stage based on call results
                stage_key = self.classifier_service.classify_lead_stage(
                    call_record.normalized_status,
                    lead.summary,
                    lead.short_summary,
                )
                
                if stage_key:
                    target_stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
                    previous_stage_id = lead.current_stage_id
                    
                    if previous_stage_id != target_stage.id:
                        lead.current_stage_id = target_stage.id
                        # If stage key is terminal, update lead status accordingly
                        if target_stage.is_terminal:
                            if stage_key == "won":
                                lead.status = "won"
                            elif stage_key == "lost" or stage_key == "not_interested":
                                lead.status = "lost"
                                
                        self.db.commit()
                        
                        # Create stage changed activity
                        self._create_or_update_activity(
                            tenant_id=tenant_id,
                            lead_id=lead.id,
                            contact_id=contact.id,
                            call_id=call_record.id,
                            activity_type="stage_changed",
                            title=f"Etapa cambiada a {target_stage.name}",
                            description=f"El lead cambió de etapa a '{target_stage.name}' basado en el análisis de la llamada.",
                            outcome=None,
                            payload_json={},
                            from_stage_id=previous_stage_id,
                            to_stage_id=target_stage.id,
                            deduplication_key=target_stage.key,
                        )
                
                # Create call ended activity
                end_reason = call_obj.get("endReason") or call_record.provider_status or "unknown"
                outcome_desc = f"Llamada finalizada. Motivo: {end_reason}."
                if call_record.duration_seconds is not None:
                    outcome_desc += f" Duración: {call_record.duration_seconds} segundos."
                    
                self._create_or_update_activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    activity_type="call_ended",
                    title="Llamada finalizada",
                    description=outcome_desc,
                    outcome=call_record.normalized_status,
                    payload_json=payload,
                )
                
            elif event_type == "call.billed":
                # Create call billed activity
                call_obj = payload.get("call") or {}
                billed_duration = (
                    call_obj.get("billedDuration") or
                    call_obj.get("billed_duration") or
                    payload.get("billedDuration") or
                    payload.get("billed_duration")
                )
                
                sip_details = call_obj.get("sipDetails") or call_obj.get("sip_details") or payload.get("sipDetails") or payload.get("sip_details")
                if not billed_duration and isinstance(sip_details, dict):
                    billed_duration = sip_details.get("billedDuration") or sip_details.get("billed_duration")
                
                desc = "Llamada facturada."
                if billed_duration:
                    desc += f" Duración facturada: {billed_duration}."
                if call_record.billed_minutes is not None:
                    desc += f" Minutos facturados: {call_record.billed_minutes} min."

                self._create_or_update_activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    activity_type="call_billed",
                    title="Llamada facturada",
                    description=desc,
                    outcome="billed",
                    payload_json=payload,
                )
                
        except Exception as e:
            # Defensive logging to ensure CRM issues never break webhook response
            logger.exception(f"Error processing CRM ingestion for Ultravox event: {e}")

    def _event_type(self, payload: dict) -> str:
        event = payload.get("event") or payload.get("event_type") or payload.get("eventType")
        if isinstance(event, str):
            return event.strip().lower()
        return "call.updated"

    def _get_metadata(self, payload: dict) -> dict:
        metadata = {}
        for candidate in (payload.get("metadata"), payload.get("meta")):
            if isinstance(candidate, dict):
                metadata.update(candidate)
        call_obj = payload.get("call")
        if isinstance(call_obj, dict):
            call_meta = call_obj.get("metadata")
            if isinstance(call_meta, dict):
                metadata.update(call_meta)
        return metadata

    def _get_initial_state(self, payload: dict) -> dict:
        call_obj = payload.get("call")
        if isinstance(call_obj, dict):
            initial_state = call_obj.get("initialState") or call_obj.get("initial_state")
            if isinstance(initial_state, dict):
                return initial_state
        return {}

    def resolve_phone(self, payload: dict, metadata: dict, initial_state: dict) -> str | None:
        phone = (
            metadata.get("user_phone") or
            metadata.get("phone") or
            initial_state.get("phone") or
            initial_state.get("user_phone")
        )
        if phone:
            return str(phone)
        
        call_obj = payload.get("call") or payload
        customer_phone = call_obj.get("customerPhone") or call_obj.get("customer_phone")
        if customer_phone:
            return str(customer_phone)
        
        direct_phone = call_obj.get("phone")
        if direct_phone:
            return str(direct_phone)
        
        sip = call_obj.get("sipDetails") or call_obj.get("sip_details")
        if isinstance(sip, dict):
            sip_from = sip.get("from")
            if sip_from:
                return str(sip_from)
                
        return None

    def resolve_name(self, metadata: dict, initial_state: dict) -> str:
        name = (
            metadata.get("user_name") or
            metadata.get("name") or
            initial_state.get("name") or
            initial_state.get("user_name")
        )
        return str(name) if name else "Lead sin nombre"

    def resolve_email(self, metadata: dict, initial_state: dict) -> str | None:
        email = (
            metadata.get("user_email") or
            metadata.get("email") or
            initial_state.get("email") or
            initial_state.get("user_email")
        )
        return str(email) if email else None

    def _create_or_update_activity(
        self,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        call_id: str | None,
        activity_type: str,
        title: str,
        description: str | None,
        outcome: str | None,
        payload_json: dict,
        from_stage_id: str | None = None,
        to_stage_id: str | None = None,
        deduplication_key: str = "",
    ) -> CrmActivity:
        activity = None
        if call_id:
            activity = self.db.scalar(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.call_id == call_id,
                    CrmActivity.activity_type == activity_type,
                    CrmActivity.deduplication_key == deduplication_key,
                )
            )

        if activity is not None:
            activity.title = title
            activity.description = description
            activity.outcome = outcome
            activity.payload_json = payload_json
            activity.from_stage_id = from_stage_id
            activity.to_stage_id = to_stage_id
            self.db.commit()
            self.db.refresh(activity)
        else:
            activity = CrmActivity(
                tenant_id=tenant_id,
                lead_id=lead_id,
                contact_id=contact_id,
                call_id=call_id,
                activity_type=activity_type,
                title=title,
                description=description,
                outcome=outcome,
                payload_json=payload_json,
                occurred_at=_utcnow(),
                from_stage_id=from_stage_id,
                to_stage_id=to_stage_id,
                deduplication_key=deduplication_key,
            )
            self.db.add(activity)
            self.db.commit()
            self.db.refresh(activity)
        return activity
