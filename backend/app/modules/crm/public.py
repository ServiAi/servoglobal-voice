"""CRM -- public API.

The one door into contacts, leads, the pipeline, the customer timeline, call
contexts and CRM voice calls. Importing this module loads only frozen DTOs
(``domain``) and ``sqlalchemy.orm.Session`` for typing; the ORM and the use
cases are imported lazily inside each method. Nothing returned here is an ORM row.

Tenant scoping: operations take ``tenant_id`` and are tenant-scoped, except
``get_contact`` / ``get_lead`` and ``CrmVoiceCalls.get`` which keep their
historical by-id semantics (callers compare ``tenant_id`` themselves).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.crm.domain.calls import (
    BookingDetection,
    CallClassification,
    CallRef,
    ContextLookup,
)
from app.modules.crm.domain.views import (
    ActivityView,
    CallContextView,
    CallState,
    ContactProfile,
    ContactRef,
    ContactSnapshot,
    CrmFunnelSnapshot,
    LeadProfile,
    LeadRef,
    LeadSnapshot,
    OutboundContactRef,
    PendingActionCandidate,
    VoiceCallView,
)

__all__ = [
    "ActivityView",
    "BookingDetection",
    "CallClassification",
    "CallContextView",
    "CallRef",
    "CallState",
    "ContactProfile",
    "ContactRef",
    "ContactSnapshot",
    "ContextLookup",
    "CrmFacade",
    "CrmFunnelSnapshot",
    "CrmVoiceCalls",
    "LeadProfile",
    "LeadRef",
    "LeadSnapshot",
    "OutboundCallLedger",
    "OutboundContactRef",
    "PendingActionCandidate",
    "VoiceCallView",
]


class CrmFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _directory(self):
        from app.modules.crm.application.directory import CrmDirectory

        return CrmDirectory(self.db)

    # -- creation ---------------------------------------------------------------
    def get_or_create_open_lead(
        self, *, tenant_id: str, phone: str, email: str | None, name: str
    ) -> tuple[ContactRef, LeadRef]:
        """Idempotent: reuses the contact for ``phone`` and its open lead."""
        from app.modules.crm.application.contact_service import CrmContactService
        from app.modules.crm.application.lead_service import CrmLeadService

        contact = CrmContactService(self.db).get_or_create_contact(tenant_id, phone, email, name)
        lead = CrmLeadService(self.db).get_or_create_open_lead(tenant_id, contact.id)
        return (
            ContactRef(id=contact.id, tenant_id=contact.tenant_id),
            LeadRef(id=lead.id, tenant_id=lead.tenant_id, contact_id=lead.contact_id, status=lead.status),
        )

    def get_or_create_contact(
        self,
        *,
        tenant_id: str,
        phone: str | None,
        email: str | None,
        name: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContactProfile:
        from app.modules.crm.application.contact_service import CrmContactService
        from app.modules.crm.application.directory import contact_profile_of

        contact = CrmContactService(self.db).get_or_create_contact(
            tenant_id, phone, email, name, dict(metadata) if metadata else None
        )
        return contact_profile_of(contact)

    # -- read-only snapshots (Voice builds SessionContextV1 from these) ------
    #
    # get_contact / get_lead are looked up by id only, NOT tenant-scoped:
    # callers must compare ``tenant_id`` themselves. That lets them fail
    # closed with a cross-tenant error instead of a silent "not found".

    def get_contact(self, contact_id: str) -> ContactSnapshot | None:
        return self._directory().snapshot_contact(contact_id)

    def get_lead(self, lead_id: str) -> LeadSnapshot | None:
        return self._directory().snapshot_lead(lead_id)

    def find_contact_by_normalized_phone(self, tenant_id: str, phone_normalized: str) -> ContactSnapshot | None:
        return self._directory().find_contact_by_normalized_phone(tenant_id, phone_normalized)

    # -- tenant-scoped profiles -------------------------------------------------
    def get_lead_profile(self, tenant_id: str, lead_id: str) -> LeadProfile | None:
        return self._directory().lead_profile(tenant_id, lead_id)

    def get_lead_profile_for_context(self, tenant_id: str, context_id: str) -> LeadProfile | None:
        return self._directory().lead_profile_for_context(tenant_id, context_id)

    def get_open_lead_for_contact(self, tenant_id: str, contact_id: str) -> LeadProfile | None:
        return self._directory().open_lead_for_contact(tenant_id, contact_id)

    def get_contact_profile(self, tenant_id: str, contact_id: str) -> ContactProfile | None:
        return self._directory().contact_profile(tenant_id, contact_id)

    def find_contact_by_phone_digits(self, tenant_id: str, phone: str | None) -> ContactProfile | None:
        """The tenant's contact whose stored phone has the same digits as ``phone``."""
        return self._directory().find_contact_by_phone_digits(tenant_id, phone)

    # -- timeline ---------------------------------------------------------------
    def record_activity(
        self,
        *,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        activity_type: str,
        title: str,
        description: str | None = None,
        payload: dict | None = None,
        outcome: str | None = None,
        call_id: str | None = None,
        deduplication_key: str = "",
    ) -> None:
        """Append an entry to the customer's CRM timeline (commits, like the
        activity service always did)."""
        from app.modules.crm.application.activity_service import CrmActivityService

        CrmActivityService(self.db).create_activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            outcome=outcome,
            call_id=call_id,
            deduplication_key=deduplication_key,
            payload_json=payload,
        )

    def stage_activity(
        self,
        *,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        activity_type: str,
        title: str,
        description: str | None = None,
        payload: dict | None = None,
        deduplication_key: str = "",
        occurred_at: datetime | None = None,
    ) -> None:
        """Add a timeline entry to the CALLER's transaction (no flush, no commit),
        for flows that must create it atomically with their own writes."""
        from app.modules.crm.application.activity_service import CrmActivityService

        CrmActivityService(self.db).stage_activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            payload_json=payload,
            deduplication_key=deduplication_key,
            occurred_at=occurred_at,
        )

    def upsert_call_activity(
        self,
        *,
        tenant_id: str,
        call_id: str,
        activity_type: str,
        deduplication_key: str,
        contact_id: str,
        lead_id: str | None,
        title: str,
        occurred_at: datetime | None,
        outcome: str | None,
        payload: dict,
    ) -> None:
        """Create-or-refresh the call's single timeline entry, in the CALLER's
        transaction (row-locked, no commit)."""
        from app.modules.crm.application.activity_service import CrmActivityService

        CrmActivityService(self.db).upsert_call_activity(
            tenant_id=tenant_id,
            call_id=call_id,
            activity_type=activity_type,
            deduplication_key=deduplication_key,
            contact_id=contact_id,
            lead_id=lead_id,
            title=title,
            occurred_at=occurred_at,
            outcome=outcome,
            payload_json=payload,
        )

    def set_lead_last_call(self, tenant_id: str, lead_id: str, call_id: str) -> None:
        """Point the lead at its most recent call (no commit)."""
        from app.modules.crm.application.lead_service import CrmLeadService

        CrmLeadService(self.db).set_last_call(tenant_id, lead_id, call_id)

    def has_activity(self, tenant_id: str, lead_id: str | None, deduplication_key: str) -> bool:
        return self._directory().has_activity(tenant_id, lead_id, deduplication_key)

    def list_lead_activities(self, tenant_id: str, lead_id: str) -> list[ActivityView]:
        return self._directory().lead_activities(tenant_id, lead_id)

    # -- call contexts ----------------------------------------------------------
    def find_call_context(self, call_context_id: str) -> CallContextView | None:
        """By CRM id or public ``context_id`` (callers that have no tenant yet)."""
        return self._directory().call_context_by_any_id(call_context_id)

    def find_call_context_for_lead(self, tenant_id: str, context_id: str) -> CallContextView | None:
        return self._directory().call_context_for_lead(tenant_id, context_id)

    def create_call_context(
        self, tenant_id: str, *, external_provider: str, context: Mapping[str, Any]
    ) -> CallContextView:
        """Persist the context a landing/voice flow collected before the call."""
        from app.modules.crm.application.call_context_service import (
            CrmCallContextService,
        )
        from app.modules.crm.application.directory import call_context_view_of

        row = CrmCallContextService(self.db).create_context(
            tenant_id, external_provider=external_provider, context=dict(context)
        )
        return call_context_view_of(row)

    def attach_external_call_id(
        self, tenant_id: str, call_context_id: str, external_call_id: str, *, external_provider: str
    ) -> CallContextView | None:
        from app.modules.crm.application.call_context_service import (
            CrmCallContextService,
        )
        from app.modules.crm.application.directory import call_context_view_of

        row = CrmCallContextService(self.db).attach_external_call_id(
            tenant_id, call_context_id, external_call_id, external_provider=external_provider
        )
        return call_context_view_of(row) if row is not None else None

    def resolve_lead_for_new_context(
        self, tenant_id: str, contact_id: str, metadata: Mapping[str, Any] | None = None
    ) -> LeadRef:
        """Find or open the lead a new form/voice context belongs to (idempotent
        per ``context_id`` / ``form_submission_id``)."""
        from sqlalchemy import select

        from app.modules.crm.application.lead_resolver_service import (
            CrmLeadResolverService,
        )
        from app.modules.crm.infrastructure.models import CrmContact

        contact = self.db.scalar(
            select(CrmContact).where(CrmContact.tenant_id == tenant_id, CrmContact.id == contact_id)
        )
        if contact is None:
            raise ValueError("Contact not found in this tenant")
        lead = CrmLeadResolverService(self.db).resolve_or_create_lead_for_new_context(
            tenant_id, contact, dict(metadata) if metadata else None
        )
        return LeadRef(id=lead.id, tenant_id=lead.tenant_id, contact_id=lead.contact_id, status=lead.status)

    # -- dashboard read-model (CRM part; Analytics/telephony composition lives outside) --
    def dashboard_funnel(
        self, tenant_id: str, date_from: datetime | None, date_to: datetime | None,
        source: str | None, campaign: str | None,
    ) -> CrmFunnelSnapshot:
        from app.modules.crm.application.dashboard_query import CrmDashboardQuery

        return CrmDashboardQuery(self.db).funnel(tenant_id, date_from, date_to, source, campaign)

    def dashboard_call_ids(self, tenant_id: str, source: str | None, campaign: str | None) -> list[str]:
        """Call ids linked to the tenant's leads of a source/campaign."""
        from app.modules.crm.application.dashboard_query import CrmDashboardQuery

        return CrmDashboardQuery(self.db).call_ids_for_leads(tenant_id, source, campaign)

    def dashboard_pending_action_candidates(
        self, tenant_id: str, source: str | None, campaign: str | None, *, offset: int, limit: int
    ) -> list[PendingActionCandidate]:
        from app.modules.crm.application.dashboard_query import CrmDashboardQuery

        return CrmDashboardQuery(self.db).pending_action_candidates(
            tenant_id, source, campaign, offset=offset, limit=limit
        )

    # -- call ingestion ---------------------------------------------------------
    def process_call_event(self, payload: dict[str, Any], call: CallRef) -> None:
        """Apply one provider call event to the lead pipeline and timeline.
        Errors are logged and swallowed, as ingestion always did."""
        from app.modules.crm.application.call_ingestion_service import (
            CrmIngestionService,
        )

        CrmIngestionService(self.db).process_call_event(payload, call)

    # -- voice calls (Telephony's CallLoadPort, for the legacy callback flow) -----
    def count_voice_calls_in_statuses(self, tenant_id: str, route_id: str, statuses: Sequence[str]) -> int:
        """CRM voice calls of the tenant holding a channel on the SIP route."""
        return CrmVoiceCalls(self.db).count_in_statuses(tenant_id, route_id, statuses)


class CrmVoiceCalls:
    """CRM's ledger of voice calls. Every write runs on the caller's session and
    NEVER commits: the caller owns the transaction (see ``VoiceCallLedger``)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _ledger(self):
        from app.modules.crm.application.voice_call_ledger import VoiceCallLedger

        return VoiceCallLedger(self.db)

    def get(self, call_id: str, *, for_update: bool = False) -> VoiceCallView | None:
        return self._ledger().get(call_id, for_update=for_update)

    def refresh(self, call_id: str) -> VoiceCallView:
        return self._ledger().refresh(call_id)

    def find_by_provider_call_id(self, provider_call_id: str) -> VoiceCallView | None:
        return self._ledger().find_by_provider_call_id(provider_call_id)

    def find_by_provider_session_id(self, provider_session_id: str) -> VoiceCallView | None:
        return self._ledger().find_by_provider_session_id(provider_session_id)

    def find_by_source_submission(self, submission_id: str, *, for_update: bool = False) -> VoiceCallView | None:
        return self._ledger().find_by_source_submission(submission_id, for_update=for_update)

    def list_for_lead(self, tenant_id: str, lead_id: str) -> list[VoiceCallView]:
        return self._ledger().list_for_lead(tenant_id, lead_id)

    def count_in_statuses(self, tenant_id: str, route_id: str, statuses: Sequence[str]) -> int:
        return self._ledger().count_in_statuses(tenant_id, route_id, statuses)

    def create(self, *, flush: bool = False, **fields: Any) -> VoiceCallView:
        return self._ledger().create(flush=flush, **fields)

    def update(self, call_id: str, **changes: Any) -> VoiceCallView:
        return self._ledger().update(call_id, **changes)

    def lock_stale_active(self, statuses: Sequence[str], updated_before: datetime) -> VoiceCallView | None:
        return self._ledger().lock_stale_active(statuses, updated_before)

    def recover_stale_starting(self, attempt_started_before: datetime) -> int:
        return self._ledger().recover_stale_starting(attempt_started_before)

    def lock_requested_callbacks(self, limit: int) -> list[VoiceCallView]:
        return self._ledger().lock_requested_callbacks(limit)

    def add_event(
        self, *, tenant_id: str, voice_call_id: str, provider: str, event_type: str, status: str,
        payload_summary: dict[str, Any],
    ) -> None:
        self._ledger().add_event(
            tenant_id=tenant_id, voice_call_id=voice_call_id, provider=provider, event_type=event_type,
            status=status, payload_summary=payload_summary,
        )

    def claim_event(
        self, *, tenant_id: str, voice_call_id: str, provider: str, event_type: str, status: str,
        dedup_key: str, payload_summary: dict[str, Any], created_at: datetime,
    ) -> bool:
        return self._ledger().claim_event(
            tenant_id=tenant_id, voice_call_id=voice_call_id, provider=provider, event_type=event_type,
            status=status, dedup_key=dedup_key, payload_summary=payload_summary, created_at=created_at,
        )


class OutboundCallLedger:
    """CRM's side of an outbound SIP call for one lead: resolves the lead's
    contact and keeps the CrmVoiceCall record in step with the call. Handed
    to Telephony (which sees only the ids and states below), so CrmLead /
    CrmContact / CrmVoiceCall rows never leave CRM. ``call_id`` is the
    CrmVoiceCall id once the call is opened (or found on an idempotent replay).
    """

    def __init__(self, db: Session, tenant_id: str, lead_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.lead_id = lead_id
        self.call_id: str | None = None

    def resolve_target(self) -> OutboundContactRef:
        profile = CrmFacade(self.db).get_lead_profile(self.tenant_id, self.lead_id)
        if profile is None:
            raise ValueError("Lead does not exist or does not belong to this tenant.")
        if profile.contact is None or profile.contact.tenant_id != self.tenant_id:
            raise ValueError("Contact associated with this lead does not exist.")
        return OutboundContactRef(
            contact_id=profile.contact.id,
            lead_id=profile.id,
            phone=profile.contact.phone,
            name=profile.contact.name,
            company=profile.contact.company,
        )

    def _calls(self) -> CrmVoiceCalls:
        return CrmVoiceCalls(self.db)

    def _own(self, call_id: str) -> VoiceCallView:
        call = self._calls().get(call_id)
        if call is None or call.tenant_id != self.tenant_id:
            raise ValueError("Idempotent voice call state is invalid.")
        return call

    def call_state(self, call_id: str) -> CallState:
        call = self._own(call_id)
        self.call_id = call.id
        return CallState(status=call.status, provider_call_id=call.provider_call_id)

    def open_call(self, *, sip_route_id: str, agent_version_id: str | None, to_phone: str, from_number: str) -> str:
        """Adds the CrmVoiceCall (flush, no commit)."""
        target = self.resolve_target()
        call = self._calls().create(
            flush=True,
            tenant_id=self.tenant_id,
            lead_id=target.lead_id,
            contact_id=target.contact_id,
            sip_route_id=sip_route_id,
            provider="livekit_sip",
            provider_agent_id=agent_version_id,
            direction="outbound",
            status="requested",
            to_phone=to_phone,
            from_number=from_number,
        )
        self.call_id = call.id
        return call.id

    def mark_dialing(self, call_id: str) -> None:
        """Commits."""
        self._calls().refresh(self._own(call_id).id)
        self._calls().update(call_id, status="dialing", started_at=datetime.now(UTC))
        self.db.commit()

    def mark_answered(self, call_id: str, provider_call_id: str | None) -> None:
        """No commit: the caller commits together with the projection."""
        self._own(call_id)
        self._calls().update(call_id, provider_call_id=provider_call_id, status="answered", answered_at=datetime.now(UTC))

    def mark_failed(self, call_id: str, call_status: str, error_code: str) -> None:
        """No commit: committed with the session failure that follows."""
        self._own(call_id)
        self._calls().refresh(call_id)
        self._calls().update(call_id, status=call_status, error_message=error_code[:255], ended_at=datetime.now(UTC))
