from __future__ import annotations

import re
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.crm import CrmContact
from app.models.identity import _utcnow

def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    # Remove all spaces, tabs, dashes, parenthesis, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)
    if not cleaned:
        return None
        
    # Colombia specific rule: if it has 10 digits and doesn't start with "+"
    # e.g., "3001112233" -> "+573001112233"
    if re.match(r"^\d{10}$", cleaned):
        cleaned = f"+57{cleaned}"
        
    return cleaned

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
            self.db.commit()
            self.db.refresh(contact)

        return contact
