from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Call
from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmPipelineStage
from app.models.identity import _utcnow
from app.services.crm_booking_detector_service import BookingDetectionResult, CrmBookingDetectorService
from app.services.crm_call_context_service import CrmCallContextService
from app.services.crm_classifier_service import CrmClassifierService
from app.services.crm_contact_service import CrmContactService, normalize_phone
from app.services.crm_context_extractor_service import CrmContextExtractorService
from app.services.crm_lead_resolver_service import CrmLeadResolverService
from app.services.crm_pipeline_service import CrmPipelineService

logger = logging.getLogger(__name__)


BOOKING_INTENT_KEYWORDS = ("agend", "reun", "cita", "confirm", "schedul", "book", "appointment")


class CrmIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.contact_service = CrmContactService(db)
        self.pipeline_service = CrmPipelineService(db)
        self.classifier_service = CrmClassifierService()
        self.context_service = CrmCallContextService(db)
        self.context_extractor = CrmContextExtractorService()
        self.lead_resolver = CrmLeadResolverService(db)
        self.booking_detector = CrmBookingDetectorService()

    def process_ultravox_event(self, payload: dict[str, Any], call_record: Call) -> None:
        try:
            tenant_id = call_record.tenant_id
            if not tenant_id:
                logger.warning("CRM ingestion skipped: call record has no tenant_id")
                return

            event_type = self._event_type(payload)

            if event_type == "call.started":
                return

            if event_type == "call.joined":
                context = self._extract_context(tenant_id, payload, call_record)
                contact = self._get_or_create_contact(tenant_id, context)
                lead = self.lead_resolver.resolve_or_create_lead_for_connected_call(
                    tenant_id=tenant_id,
                    call=call_record,
                    contact=contact,
                    metadata=self._lead_metadata(context),
                    stage_key="connected",
                )
                self._enrich_contact_from_context(contact, context)
                self._move_lead_to_stage(
                    tenant_id=tenant_id,
                    lead=lead,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    stage_key="connected",
                    description="El lead avanzo automaticamente a 'Conectado' al establecerse la llamada.",
                )
                self._create_or_update_activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    contact_id=contact.id,
                    call_id=call_record.id,
                    activity_type="call_joined",
                    title="Llamada establecida",
                    description="El cliente se conecto a la llamada exitosamente.",
                    outcome="connected",
                    payload_json=payload,
                )
                return

            if event_type == "call.ended":
                lead = self.lead_resolver.resolve_existing_lead_for_call(tenant_id, call_record)
                context = None
                contact = lead.contact if lead is not None else None

                if lead is None and call_record.joined_at is not None:
                    context = self._extract_context(tenant_id, payload, call_record)
                    contact = self._get_or_create_contact(tenant_id, context)
                    lead = self.lead_resolver.resolve_or_create_lead_for_connected_call(
                        tenant_id=tenant_id,
                        call=call_record,
                        contact=contact,
                        metadata=self._lead_metadata(context),
                        stage_key="connected",
                    )

                if lead is None or contact is None:
                    return

                if context is None:
                    context = self._extract_context(tenant_id, payload, call_record)
                self._enrich_contact_from_context(contact, context)
                self._enrich_lead_from_context(lead, context)
                self._update_lead_summary(lead, payload, call_record)

                booking = self.booking_detector.detect_successful_booking(payload)
                if booking.created:
                    self._move_lead_to_stage(
                        tenant_id=tenant_id,
                        lead=lead,
                        contact_id=contact.id,
                        call_id=call_record.id,
                        stage_key="scheduled",
                        description="El lead cambio a 'Agendado' porque se verifico un evento real de agenda.",
                    )
                    self._create_booking_activity(tenant_id, lead, contact.id, call_record.id, booking, payload)
                else:
                    stage_key = self.classifier_service.classify_lead_stage(
                        call_record.normalized_status,
                        lead.summary,
                        lead.short_summary,
                    )
                    if self._has_booking_intent(lead.summary, lead.short_summary):
                        lead.next_action = "confirm_booking"
                        if stage_key is None:
                            stage_key = "follow_up"
                        self.db.commit()
                        self.db.refresh(lead)
                    if stage_key:
                        self._move_lead_to_stage(
                            tenant_id=tenant_id,
                            lead=lead,
                            contact_id=contact.id,
                            call_id=call_record.id,
                            stage_key=stage_key,
                            description="El lead cambio de etapa basado en reglas deterministicas de la llamada.",
                        )

                self._create_call_ended_activity(tenant_id, lead, contact.id, call_record.id, payload, call_record)
                return

            if event_type == "call.billed":
                lead = self.lead_resolver.resolve_existing_lead_for_call(tenant_id, call_record)
                if lead is None:
                    return
                self._create_call_billed_activity(tenant_id, lead, lead.contact_id, call_record.id, payload, call_record)
                return

        except Exception as e:
            logger.exception(f"Error processing CRM ingestion for Ultravox event: {e}")

    def _extract_context(self, tenant_id: str, payload: dict[str, Any], call_record: Call) -> dict[str, Any]:
        call_context = self.context_service.find_context_from_payload(
            tenant_id,
            payload,
            external_provider=call_record.external_provider,
        )
        return self.context_extractor.extract(payload, call_record=call_record, call_context=call_context)

    def _get_or_create_contact(self, tenant_id: str, context: dict[str, Any]) -> CrmContact:
        return self.contact_service.get_or_create_contact(
            tenant_id=tenant_id,
            phone=context.get("phone"),
            email=context.get("email"),
            name=context.get("name") or "Lead sin nombre",
            metadata=self._contact_metadata(context),
        )

    def _contact_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "company": context.get("company"),
            "source": context.get("source"),
            "field_sources": context.get("field_sources") or {},
        }
        return {key: value for key, value in metadata.items() if value not in (None, "")}

    def _lead_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "interest": context.get("interest"),
            "industry": context.get("industry"),
            "use_case": context.get("use_case"),
            "volume": context.get("volume"),
            "pain_point": context.get("pain_point"),
            "budget_range": context.get("budget_range"),
            "intent_level": context.get("intent_level"),
            "source": context.get("source") or context.get("utm_source"),
            "campaign": context.get("campaign") or context.get("utm_campaign"),
        }

    def _enrich_contact_from_context(self, contact: CrmContact, context: dict[str, Any]) -> None:
        phone = context.get("phone")
        phone_normalized = normalize_phone(phone)
        if context.get("name") and (contact.name == "Lead sin nombre" or not contact.name):
            contact.name = context["name"]
        if context.get("email") and not contact.email:
            contact.email = context["email"]
        if phone and not contact.phone:
            contact.phone = phone
        if phone_normalized and not contact.phone_normalized:
            contact.phone_normalized = phone_normalized
        if context.get("company") and not contact.company:
            contact.company = context["company"]
        if context.get("source") and not contact.source:
            contact.source = context["source"]

        merged = dict(contact.metadata_json or {})
        for key, value in self._contact_metadata(context).items():
            if value not in (None, ""):
                merged[key] = value
        contact.metadata_json = merged
        self.db.commit()
        self.db.refresh(contact)

    def _enrich_lead_from_context(self, lead: CrmLead, context: dict[str, Any]) -> None:
        for field, value in self._lead_metadata(context).items():
            if value and not getattr(lead, field):
                setattr(lead, field, value)
        lead.last_call_id = lead.last_call_id or lead.created_from_call_id
        self.db.commit()
        self.db.refresh(lead)

    def _update_lead_summary(self, lead: CrmLead, payload: dict[str, Any], call_record: Call) -> None:
        call_obj = payload.get("call") if isinstance(payload.get("call"), dict) else {}
        summary = call_obj.get("summary") or call_record.summary
        short_summary = call_obj.get("shortSummary") or call_obj.get("short_summary") or call_record.short_summary
        if summary:
            lead.summary = summary
        if short_summary:
            lead.short_summary = short_summary
        if call_record.id:
            lead.last_call_id = call_record.id
        self.db.commit()
        self.db.refresh(lead)

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
            existing_activity = self.db.scalar(
                select(CrmActivity).where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.call_id == call_id,
                    CrmActivity.activity_type == "stage_changed",
                    CrmActivity.deduplication_key == target_stage.key,
                )
            )
            if existing_activity is None:
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
                    from_stage_id=None,
                    to_stage_id=target_stage.id,
                    deduplication_key=target_stage.key,
                )
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

    def _has_booking_intent(self, summary: str | None, short_summary: str | None) -> bool:
        text = " ".join(filter(None, [summary, short_summary])).lower()
        return any(keyword in text for keyword in BOOKING_INTENT_KEYWORDS)

    def _create_booking_activity(
        self,
        tenant_id: str,
        lead: CrmLead,
        contact_id: str,
        call_id: str | None,
        booking: BookingDetectionResult,
        payload: dict[str, Any],
    ) -> None:
        description_parts = ["Evento de agenda verificado por tool."]
        if booking.event_id:
            description_parts.append(f"event_id={booking.event_id}.")
        if booking.start_time:
            description_parts.append(f"inicio={booking.start_time}.")
        self._create_or_update_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact_id,
            call_id=call_id,
            activity_type="booking_detected",
            title="Agenda verificada",
            description=" ".join(description_parts),
            outcome="scheduled",
            payload_json={},
            deduplication_key="booking_detected",
        )

    def _create_call_ended_activity(
        self,
        tenant_id: str,
        lead: CrmLead,
        contact_id: str,
        call_id: str | None,
        payload: dict[str, Any],
        call_record: Call,
    ) -> None:
        call_obj = payload.get("call") if isinstance(payload.get("call"), dict) else {}
        end_reason = call_obj.get("endReason") or call_obj.get("end_reason") or call_record.provider_status or "unknown"
        outcome_desc = f"Llamada finalizada. Motivo: {end_reason}."
        if call_record.duration_seconds is not None:
            outcome_desc += f" Duracion: {call_record.duration_seconds} segundos."
        self._create_or_update_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact_id,
            call_id=call_id,
            activity_type="call_ended",
            title="Llamada finalizada",
            description=outcome_desc,
            outcome=call_record.normalized_status,
            payload_json=payload,
        )

    def _create_call_billed_activity(
        self,
        tenant_id: str,
        lead: CrmLead,
        contact_id: str,
        call_id: str | None,
        payload: dict[str, Any],
        call_record: Call,
    ) -> None:
        call_obj = payload.get("call") if isinstance(payload.get("call"), dict) else {}
        billed_duration = (
            call_obj.get("billedDuration")
            or call_obj.get("billed_duration")
            or payload.get("billedDuration")
            or payload.get("billed_duration")
        )
        sip_details = call_obj.get("sipDetails") or call_obj.get("sip_details") or payload.get("sipDetails") or payload.get("sip_details")
        if not billed_duration and isinstance(sip_details, dict):
            billed_duration = sip_details.get("billedDuration") or sip_details.get("billed_duration")

        desc = "Llamada facturada."
        if billed_duration:
            desc += f" Duracion facturada: {billed_duration}."
        if call_record.billed_minutes is not None:
            desc += f" Minutos facturados: {call_record.billed_minutes} min."

        self._create_or_update_activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            contact_id=contact_id,
            call_id=call_id,
            activity_type="call_billed",
            title="Llamada facturada",
            description=desc,
            outcome="billed",
            payload_json=payload,
        )

    def _event_type(self, payload: dict[str, Any]) -> str:
        event = payload.get("event") or payload.get("event_type") or payload.get("eventType")
        if isinstance(event, str):
            return event.strip().lower()
        return "call.updated"

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
            return activity

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
