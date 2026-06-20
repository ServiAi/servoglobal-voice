from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmActivity, CrmLead, CrmPipelineStage


class CrmActivityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_activity(
        self,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        activity_type: str,
        title: str,
        description: str | None = None,
        outcome: str | None = None,
        call_id: str | None = None,
        from_stage_id: str | None = None,
        to_stage_id: str | None = None,
        deduplication_key: str = "",
        payload_json: dict | None = None,
    ) -> CrmActivity:
        activity = CrmActivity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            outcome=outcome,
            occurred_at=datetime.now(UTC),
            call_id=call_id,
            from_stage_id=from_stage_id,
            to_stage_id=to_stage_id,
            deduplication_key=deduplication_key,
            payload_json=payload_json or {},
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity

    def get_activities(
        self,
        tenant_id: str,
        lead_id: str | None = None,
        contact_id: str | None = None,
        activity_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrmActivity]:
        query = (
            select(CrmActivity)
            .where(CrmActivity.tenant_id == tenant_id)
        )

        if lead_id:
            query = query.where(CrmActivity.lead_id == lead_id)
        if contact_id:
            query = query.where(CrmActivity.contact_id == contact_id)
        if activity_type:
            query = query.where(CrmActivity.activity_type == activity_type)
        if date_from:
            query = query.where(CrmActivity.occurred_at >= date_from)
        if date_to:
            query = query.where(CrmActivity.occurred_at <= date_to)

        query = query.order_by(CrmActivity.occurred_at.desc()).offset(offset).limit(limit)

        return list(self.db.scalars(query).all())

    def get_activities_for_lead(
        self,
        tenant_id: str,
        lead_id: str,
    ) -> list[CrmActivity]:
        return list(
            self.db.scalars(
                select(CrmActivity)
                .where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.lead_id == lead_id,
                )
                .order_by(CrmActivity.occurred_at.desc())
            ).all()
        )

    def get_last_activity_at(
        self,
        tenant_id: str,
        lead_id: str,
    ) -> datetime | None:
        activity = self.db.scalar(
            select(CrmActivity.occurred_at)
            .where(
                CrmActivity.tenant_id == tenant_id,
                CrmActivity.lead_id == lead_id,
            )
            .order_by(CrmActivity.occurred_at.desc())
            .limit(1)
        )
        return activity