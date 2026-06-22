from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity
from app.models.identity import _utcnow
from app.services.crm_contact_service import CrmContactService, normalize_phone
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
            phone = self.resolve_phone(payload, metadata, initial_state) or call_record.customer_phone
            email = self.resolve_email(metadata, initial_state)
            name = self.resolve_name(metadata, initial_state)

            lead = self._get_lead_for_call(tenant_id, call_record.id)
            if lead is not None:
                contact = lead.contact
                self._enrich_contact_from_event(contact, phone, email, name, metadata)
                if call_record.id:
                    lead.last_call_id = call_record.id
                self.lead_service._enrich_lead_fields(lead, self._lead_metadata(metadata, initial_state))
                self.db.commit()
                self.db.refresh(lead)
            else:
                # 1. Resolve or create contact
                contact = self.contact_service.get_or_create_contact(
                    tenant_id=tenant_id,
                    phone=phone,
                    email=email,
                    name=name,
                    metadata=metadata,
                )

                # 2. Resolve or create lead
                lead = self.lead_service.get_or_create_open_lead(
                    tenant_id=tenant_id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    metadata=self._lead_metadata(metadata, initial_state),
                )

            created_calendar_event = self._has_successful_tool_call(payload, "crear_evento")
            
            # Handle specific events
            if event_type == "call.started":
                self._move_lead_to_stage(
                    tenant_id=tenant_id,
                    lead=lead,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    stage_key="contacted",
                    description="El lead avanzó automáticamente a 'Contactado' al iniciarse el intento de llamada.",
                )
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
                self._move_lead_to_stage(
                    tenant_id=tenant_id,
                    lead=lead,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    stage_key="connected",
                    description="El lead avanzó automáticamente a 'Conectado' al establecerse la llamada.",
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
                
                if created_calendar_event:
                    stage_key = "scheduled"
                else:
                    # Classify lead stage based on call results. "Agendado" is only set by crear_evento.
                    stage_key = self.classifier_service.classify_lead_stage(
                        call_record.normalized_status,
                        lead.summary,
                        lead.short_summary,
                    )

                if stage_key:
                    reason = (
                        "El lead cambió a 'Agendado' porque se ejecutó correctamente la tool crear_evento."
                        if stage_key == "scheduled"
                        else "El lead cambió de etapa basado en el análisis de la llamada."
                    )
                    self._move_lead_to_stage(
                        tenant_id=tenant_id,
                        lead=lead,
                        contact_id=contact.id,
                        call_id=call_record.id,
                        stage_key=stage_key,
                        description=reason,
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

            if created_calendar_event and event_type != "call.ended":
                self._move_lead_to_stage(
                    tenant_id=tenant_id,
                    lead=lead,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    stage_key="scheduled",
                    description="El lead cambió a 'Agendado' porque se ejecutó correctamente la tool crear_evento.",
                )
                
        except Exception as e:
            # Defensive logging to ensure CRM issues never break webhook response
            logger.exception(f"Error processing CRM ingestion for Ultravox event: {e}")

    def _get_lead_for_call(self, tenant_id: str, call_id: str | None) -> CrmLead | None:
        if not call_id:
            return None
        return self.db.scalar(
            select(CrmLead)
            .where(
                CrmLead.tenant_id == tenant_id,
                (CrmLead.created_from_call_id == call_id) | (CrmLead.last_call_id == call_id),
            )
            .order_by(CrmLead.updated_at.desc())
            .limit(1)
        )

    def _lead_metadata(self, metadata: dict, initial_state: dict) -> dict:
        return {
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

    def _enrich_contact_from_event(
        self,
        contact: CrmContact,
        phone: str | None,
        email: str | None,
        name: str | None,
        metadata: dict,
    ) -> None:
        phone_normalized = normalize_phone(phone)
        if name and (contact.name == "Lead sin nombre" or not contact.name):
            contact.name = name
        if email and not contact.email:
            contact.email = email
        if phone and not contact.phone:
            contact.phone = phone
        if phone_normalized and not contact.phone_normalized:
            contact.phone_normalized = phone_normalized
        company = metadata.get("company")
        if company and not contact.company:
            contact.company = company
        source = metadata.get("source")
        if source and not contact.source:
            contact.source = source
        if isinstance(contact.metadata_json, dict):
            contact.metadata_json = {**contact.metadata_json, **metadata}
        else:
            contact.metadata_json = metadata

    def _move_lead_to_stage(
        self,
        tenant_id: str,
        lead: CrmLead,
        contact_id: str,
        call_id: str | None,
        stage_key: str,
        description: str,
    ) -> None:
        target_stage = self.pipeline_service.get_stage_by_key(tenant_id, stage_key)
        current_stage = self.db.get(CrmPipelineStage, lead.current_stage_id)
        if current_stage and current_stage.id == target_stage.id:
            return
        if current_stage and current_stage.position > target_stage.position:
            return

        previous_stage_id = lead.current_stage_id
        lead.current_stage_id = target_stage.id
        if target_stage.is_terminal:
            if stage_key == "won":
                lead.status = "won"
            elif stage_key in {"lost", "not_interested"}:
                lead.status = "lost"

        self.db.commit()
        self.db.refresh(lead)
        self._create_or_update_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact_id,
            call_id=call_id,
            activity_type="stage_changed",
            title=f"Etapa cambiada a {target_stage.name}",
            description=description,
            outcome=None,
            payload_json={},
            from_stage_id=previous_stage_id,
            to_stage_id=target_stage.id,
            deduplication_key=target_stage.key,
        )

    def _has_successful_tool_call(self, payload: Any, tool_name: str) -> bool:
        expected_name = tool_name.strip().lower()
        for item in self._walk_payload(payload):
            if not isinstance(item, dict):
                continue
            candidate_name = self._tool_name(item)
            if candidate_name != expected_name:
                continue
            if self._tool_failed(item):
                continue
            return True
        return False

    def _walk_payload(self, value: Any):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._walk_payload(nested)
        elif isinstance(value, list):
            for item in value:
                yield from self._walk_payload(item)

    def _tool_name(self, item: dict) -> str | None:
        for key in ("toolName", "tool_name", "functionName", "function_name", "name"):
            value = item.get(key)
            if isinstance(value, str):
                return value.strip().lower()

        for key in ("tool", "function"):
            nested = item.get(key)
            if isinstance(nested, dict):
                value = nested.get("name")
                if isinstance(value, str):
                    return value.strip().lower()
        return None

    def _tool_failed(self, item: dict) -> bool:
        status_value = item.get("status") or item.get("outcome")
        result = item.get("result")
        if isinstance(result, dict):
            status_value = status_value or result.get("status") or result.get("outcome")
        if not isinstance(status_value, str):
            return False
        return status_value.strip().lower() in {"error", "failed", "failure", "rejected"}

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
