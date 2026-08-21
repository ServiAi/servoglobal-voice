from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.services.crm_lead_service import CrmLeadService


class CrmLeadServiceDeleteAllTests(Integration2ATestCase):
    def test_delete_all_leads_purges_orphan_contacts_when_no_leads_exist(self) -> None:
        with SessionLocal() as db:
            db.add(
                CrmContact(
                    tenant_id=self.tenant.id,
                    name="Orphan Contact",
                    email="orphan@example.com",
                    phone="+573001112233",
                )
            )
            db.commit()

        with SessionLocal() as db:
            deleted_count = CrmLeadService(db).delete_all_leads(self.tenant.id)

        self.assertEqual(deleted_count, 0)
        with SessionLocal() as db:
            self.assertIsNone(
                db.scalar(select(CrmContact).where(CrmContact.tenant_id == self.tenant.id))
            )

    def test_delete_all_leads_still_purges_leads_and_contacts_together(self) -> None:
        with SessionLocal() as db:
            stage = CrmPipelineStage(
                tenant_id=self.tenant.id, key="new", name="Nuevo", position=1, is_default=True
            )
            contact = CrmContact(
                tenant_id=self.tenant.id,
                name="Pedro Gomez",
                email="lead@example.com",
                phone="+573001112233",
            )
            db.add_all([stage, contact])
            db.commit()
            db.refresh(stage)
            db.refresh(contact)
            lead = CrmLead(
                tenant_id=self.tenant.id,
                contact_id=contact.id,
                current_stage_id=stage.id,
                status="open",
            )
            db.add(lead)
            db.commit()

        with SessionLocal() as db:
            deleted_count = CrmLeadService(db).delete_all_leads(self.tenant.id)

        self.assertEqual(deleted_count, 1)
        with SessionLocal() as db:
            self.assertIsNone(
                db.scalar(select(CrmLead).where(CrmLead.tenant_id == self.tenant.id))
            )
            self.assertIsNone(
                db.scalar(select(CrmContact).where(CrmContact.tenant_id == self.tenant.id))
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
