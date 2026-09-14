from __future__ import annotations

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.services.contact_resolution_service import (
    ContactResolutionService,
    CrossTenantResolutionError,
)


class ContactResolutionServiceTests(Integration2ATestCase):
    def _seed_contact(self, tenant_id: str, *, phone_normalized: str = "+573001112233", name: str = "Carlos Pérez", email: str | None = None) -> str:
        with SessionLocal() as db:
            contact = CrmContact(
                tenant_id=tenant_id, name=name, phone="3001112233",
                phone_normalized=phone_normalized, email=email or f"{phone_normalized.lstrip('+')}@example.com",
            )
            db.add(contact)
            db.commit()
            db.refresh(contact)
            return contact.id

    def _seed_lead(self, tenant_id: str, contact_id: str, *, status: str = "open", stage_key: str = "qualified", campaign: str | None = None) -> str:
        with SessionLocal() as db:
            stage = db.query(CrmPipelineStage).filter_by(tenant_id=tenant_id, key=stage_key).first()
            if stage is None:
                stage = CrmPipelineStage(tenant_id=tenant_id, key=stage_key, name=stage_key.title(), position=1, is_default=True)
                db.add(stage)
                db.commit()
                db.refresh(stage)
            lead = CrmLead(tenant_id=tenant_id, contact_id=contact_id, current_stage_id=stage.id, status=status, campaign=campaign)
            db.add(lead)
            db.commit()
            db.refresh(lead)
            return lead.id

    def _service(self) -> tuple[ContactResolutionService, "SessionLocal"]:
        db = SessionLocal()
        return ContactResolutionService(db), db

    # -- caller only / phone resolution --

    def test_unknown_phone_resolves_to_caller_only(self) -> None:
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, phone="+573009998877")
            self.assertEqual(ctx.caller.phone, "+573009998877")
            self.assertIsNone(ctx.contact)
            self.assertIsNone(ctx.lead)
        finally:
            db.close()

    def test_known_phone_resolves_contact(self) -> None:
        self._seed_contact(self.tenant.id)
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, phone="+573001112233")
            self.assertIsNotNone(ctx.contact)
            self.assertEqual(ctx.contact.name, "Carlos Pérez")
            self.assertIsNone(ctx.lead)
        finally:
            db.close()

    def test_no_phone_and_no_ids_resolves_to_fully_empty_context(self) -> None:
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id)
            self.assertIsNone(ctx.caller)
            self.assertIsNone(ctx.contact)
            self.assertIsNone(ctx.lead)
        finally:
            db.close()

    def test_never_auto_creates_a_contact_for_an_unknown_phone(self) -> None:
        service, db = self._service()
        try:
            service.resolve(tenant_id=self.tenant.id, phone="+573009998877")
        finally:
            db.close()
        with SessionLocal() as check_db:
            self.assertIsNone(check_db.query(CrmContact).filter_by(tenant_id=self.tenant.id).first())

    def test_invalid_phone_still_resolves_caller_but_no_contact_lookup_crash(self) -> None:
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, phone="not-a-phone-number")
            self.assertEqual(ctx.caller.phone, "not-a-phone-number")
            self.assertIsNone(ctx.contact)
        finally:
            db.close()

    # -- explicit trusted IDs --

    def test_trusted_lead_id_resolves_lead_and_its_contact(self) -> None:
        contact_id = self._seed_contact(self.tenant.id)
        lead_id = self._seed_lead(self.tenant.id, contact_id, campaign="Cobranza septiembre")
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, lead_id=lead_id, trusted_ids=True)
            self.assertEqual(ctx.lead.id, lead_id)
            self.assertEqual(ctx.lead.status, "open")
            self.assertEqual(ctx.lead.stage, "qualified")
            self.assertEqual(ctx.contact.id, contact_id)
            self.assertEqual(ctx.campaign.name, "Cobranza septiembre")
        finally:
            db.close()

    def test_trusted_contact_id_resolves_contact_without_lead(self) -> None:
        contact_id = self._seed_contact(self.tenant.id)
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, contact_id=contact_id, trusted_ids=True)
            self.assertEqual(ctx.contact.id, contact_id)
            self.assertIsNone(ctx.lead)
        finally:
            db.close()

    def test_untrusted_ids_are_ignored_even_if_valid(self) -> None:
        contact_id = self._seed_contact(self.tenant.id)
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, contact_id=contact_id, trusted_ids=False)
            self.assertIsNone(ctx.contact)
        finally:
            db.close()

    def test_phone_lookup_is_skipped_when_trusted_ids_are_used(self) -> None:
        contact_id = self._seed_contact(self.tenant.id, phone_normalized="+573001112233")
        other_contact_id = self._seed_contact(self.tenant.id, phone_normalized="+573004445566", name="Otra Persona")
        service, db = self._service()
        try:
            ctx = service.resolve(
                tenant_id=self.tenant.id, phone="+573004445566", contact_id=contact_id, trusted_ids=True
            )
            self.assertEqual(ctx.contact.id, contact_id)
            self.assertNotEqual(ctx.contact.id, other_contact_id)
        finally:
            db.close()

    # -- multi-tenant isolation --

    def test_cross_tenant_lead_id_is_rejected(self) -> None:
        other_tenant, _ = self._seed_tenant_user(slug="contact-res-tenant-b", email="crb@example.com")
        contact_id = self._seed_contact(other_tenant.id)
        lead_id = self._seed_lead(other_tenant.id, contact_id)
        service, db = self._service()
        try:
            with self.assertRaises(CrossTenantResolutionError):
                service.resolve(tenant_id=self.tenant.id, lead_id=lead_id, trusted_ids=True)
        finally:
            db.close()

    def test_cross_tenant_contact_id_is_rejected(self) -> None:
        other_tenant, _ = self._seed_tenant_user(slug="contact-res-tenant-c", email="crc@example.com")
        contact_id = self._seed_contact(other_tenant.id)
        service, db = self._service()
        try:
            with self.assertRaises(CrossTenantResolutionError):
                service.resolve(tenant_id=self.tenant.id, contact_id=contact_id, trusted_ids=True)
        finally:
            db.close()

    def test_cross_tenant_phone_lookup_never_matches_another_tenants_contact(self) -> None:
        other_tenant, _ = self._seed_tenant_user(slug="contact-res-tenant-d", email="crd@example.com")
        self._seed_contact(other_tenant.id, phone_normalized="+573001112233")
        service, db = self._service()
        try:
            ctx = service.resolve(tenant_id=self.tenant.id, phone="+573001112233")
            self.assertIsNone(ctx.contact)
        finally:
            db.close()

    def test_mismatched_lead_and_contact_ids_are_rejected(self) -> None:
        contact_a = self._seed_contact(self.tenant.id, phone_normalized="+573001112233")
        contact_b = self._seed_contact(self.tenant.id, phone_normalized="+573004445566", name="Otra Persona")
        lead_id = self._seed_lead(self.tenant.id, contact_a)
        service, db = self._service()
        try:
            with self.assertRaises(CrossTenantResolutionError):
                service.resolve(tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_b, trusted_ids=True)
        finally:
            db.close()

    # -- variables / source pass-through --

    def test_variables_and_source_pass_through(self) -> None:
        service, db = self._service()
        try:
            ctx = service.resolve(
                tenant_id=self.tenant.id, source="outbound", variables={"debt_amount": 850000}
            )
            self.assertEqual(ctx.source, "outbound")
            self.assertEqual(ctx.variables, {"debt_amount": 850000})
        finally:
            db.close()
