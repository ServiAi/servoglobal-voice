from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.mixins import _utcnow
from app.modules.crm.domain.contacts import normalize_phone
from app.modules.crm.infrastructure.models import CrmContact


class CrmContactService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_contact(
        self,
        tenant_id: str,
        phone: str | None,
        email: str | None,
        name: str | None,
        metadata: dict | None = None,
        *,
        _retry: bool = True,
    ) -> CrmContact:
        phone_normalized = normalize_phone(phone)
        contact = None

        # Try to find by normalized phone
        if phone_normalized:
            contact = self.db.scalar(
                select(CrmContact).where(
                    CrmContact.tenant_id == tenant_id,
                    CrmContact.phone_normalized == phone_normalized,
                )
            )

        # Fallback to email
        if contact is None and email:
            contact = self.db.scalar(
                select(CrmContact).where(
                    CrmContact.tenant_id == tenant_id,
                    CrmContact.email == email,
                )
            )

        now = _utcnow()
        meta_dict = metadata or {}

        if contact is not None:
            # Contact exists, update last seen and enrich fields if empty
            contact.last_seen_at = now
            if name and (contact.name == "Lead sin nombre" or not contact.name):
                contact.name = name
            if email and not contact.email:
                contact.email = email
            if phone and not contact.phone:
                contact.phone = phone
            if phone_normalized and not contact.phone_normalized:
                contact.phone_normalized = phone_normalized
                
            company = meta_dict.get("company")
            if company and not contact.company:
                contact.company = company
                
            source = meta_dict.get("source")
            if source and not contact.source:
                contact.source = source
                
            if isinstance(contact.metadata_json, dict):
                contact.metadata_json = {**contact.metadata_json, **meta_dict}
            else:
                contact.metadata_json = meta_dict
                
            self.db.commit()
            self.db.refresh(contact)
        else:
            # Create a new contact
            contact = CrmContact(
                tenant_id=tenant_id,
                name=name or "Lead sin nombre",
                phone=phone,
                phone_normalized=phone_normalized,
                email=email,
                company=meta_dict.get("company"),
                source=meta_dict.get("source"),
                first_seen_at=now,
                last_seen_at=now,
                status="active",
                metadata_json=meta_dict,
            )
            self.db.add(contact)
            try:
                self.db.commit()
            except IntegrityError:
                # A concurrent request created the same contact (unique per tenant+phone and
                # tenant+email): discard ours and enrich theirs. One retry only.
                self.db.rollback()
                if not _retry:
                    raise
                return self.get_or_create_contact(tenant_id, phone, email, name, metadata, _retry=False)
            self.db.refresh(contact)

        return contact
