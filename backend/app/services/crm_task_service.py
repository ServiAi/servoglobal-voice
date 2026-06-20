from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmActivity, CrmContact, CrmLead, CrmTask
from app.models.identity import TenantMembership, User
from app.services.crm_activity_service import CrmActivityService


VALID_TASK_STATUSES = {"pending", "done", "cancelled", "overdue"}
VALID_TASK_PRIORITIES = {"low", "medium", "high"}


class CrmTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.activity_service = CrmActivityService(db)

    def _validate_tenant_resources(
        self,
        tenant_id: str,
        lead_id: str | None = None,
        contact_id: str | None = None,
        assigned_to_user_id: str | None = None,
    ) -> None:
        if lead_id:
            lead = self.db.scalar(
                select(CrmLead).where(
                    CrmLead.id == lead_id,
                    CrmLead.tenant_id == tenant_id,
                )
            )
            if not lead:
                raise ValueError("Lead not found in this tenant")

        if contact_id:
            contact = self.db.scalar(
                select(CrmContact).where(
                    CrmContact.id == contact_id,
                    CrmContact.tenant_id == tenant_id,
                )
            )
            if not contact:
                raise ValueError("Contact not found in this tenant")

        if assigned_to_user_id:
            membership = self.db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == assigned_to_user_id,
                    TenantMembership.status == "active",
                )
            )
            if not membership:
                raise ValueError("Assigned user is not an active member of this tenant")

    def create_task(
        self,
        tenant_id: str,
        title: str,
        lead_id: str | None = None,
        contact_id: str | None = None,
        description: str | None = None,
        due_at: datetime | None = None,
        priority: str = "medium",
        assigned_to_user_id: str | None = None,
    ) -> CrmTask:
        self._validate_tenant_resources(
            tenant_id, lead_id=lead_id, contact_id=contact_id,
            assigned_to_user_id=assigned_to_user_id,
        )

        if priority not in VALID_TASK_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}. Must be one of {VALID_TASK_PRIORITIES}")

        # Resolve contact_id from lead if not provided
        resolved_contact_id = contact_id
        if lead_id and not resolved_contact_id:
            lead = self.db.scalar(
                select(CrmLead).where(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
            )
            if lead:
                resolved_contact_id = lead.contact_id

        task = CrmTask(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=resolved_contact_id,
            assigned_to_user_id=assigned_to_user_id,
            title=title,
            description=description,
            due_at=due_at,
            status="pending",
            priority=priority,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        if lead_id and resolved_contact_id:
            self.activity_service.create_activity(
                tenant_id=tenant_id,
                lead_id=lead_id,
                contact_id=resolved_contact_id,
                activity_type="task_created",
                title=f"Tarea creada: {title}",
                description=description,
            )

        return task

    def update_task(
        self,
        tenant_id: str,
        task_id: str,
        **kwargs,
    ) -> CrmTask | None:
        task = self.db.scalar(
            select(CrmTask).where(
                CrmTask.id == task_id,
                CrmTask.tenant_id == tenant_id,
            )
        )
        if not task:
            return None

        # Validate status if being changed
        if "status" in kwargs and kwargs["status"] is not None:
            if kwargs["status"] not in VALID_TASK_STATUSES:
                raise ValueError(f"Invalid status: {kwargs['status']}")
            old_status = task.status

        # Validate priority if being changed
        if "priority" in kwargs and kwargs["priority"] is not None:
            if kwargs["priority"] not in VALID_TASK_PRIORITIES:
                raise ValueError(f"Invalid priority: {kwargs['priority']}")

        # Validate assigned_to_user_id if being changed
        if "assigned_to_user_id" in kwargs and kwargs["assigned_to_user_id"] is not None:
            self._validate_tenant_resources(
                tenant_id,
                assigned_to_user_id=kwargs["assigned_to_user_id"],
            )

        for key, value in kwargs.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)

        self.db.commit()
        self.db.refresh(task)

        # Create activity for update
        has_lead = task.lead_id is not None
        has_contact = task.contact_id is not None

        if has_lead and has_contact:
            if "status" in kwargs and kwargs.get("status") == "done":
                self.activity_service.create_activity(
                    tenant_id=tenant_id,
                    lead_id=task.lead_id,
                    contact_id=task.contact_id,
                    activity_type="task_completed",
                    title=f"Tarea completada: {task.title}",
                )
            else:
                self.activity_service.create_activity(
                    tenant_id=tenant_id,
                    lead_id=task.lead_id,
                    contact_id=task.contact_id,
                    activity_type="task_updated",
                    title=f"Tarea actualizada: {task.title}",
                )

        return task

    def delete_task(
        self,
        tenant_id: str,
        task_id: str,
    ) -> bool:
        task = self.db.scalar(
            select(CrmTask).where(
                CrmTask.id == task_id,
                CrmTask.tenant_id == tenant_id,
            )
        )
        if not task:
            return False

        self.db.delete(task)
        self.db.commit()
        return True

    def get_task(
        self,
        tenant_id: str,
        task_id: str,
    ) -> CrmTask | None:
        return self.db.scalar(
            select(CrmTask).where(
                CrmTask.id == task_id,
                CrmTask.tenant_id == tenant_id,
            )
        )

    def list_tasks(
        self,
        tenant_id: str,
        lead_id: str | None = None,
        contact_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[CrmTask]:
        query = select(CrmTask).where(CrmTask.tenant_id == tenant_id)

        if lead_id:
            query = query.where(CrmTask.lead_id == lead_id)
        if contact_id:
            query = query.where(CrmTask.contact_id == contact_id)
        if status:
            query = query.where(CrmTask.status == status)
        if priority:
            query = query.where(CrmTask.priority == priority)

        return list(self.db.scalars(query.order_by(CrmTask.created_at.desc())).all())