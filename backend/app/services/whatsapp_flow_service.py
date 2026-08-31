from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.integrations import TenantWhatsAppFlow
from app.models.voice_context import TenantVoiceContextSchema
from app.schemas.whatsapp_flows import (
    FlowBuilder,
    MetaFlowValidationError,
    WhatsAppFlowCompileResponse,
    WhatsAppFlowCreateRequest,
    WhatsAppFlowResponse,
    WhatsAppFlowUpdateRequest,
)
from app.services.integration_event_service import IntegrationEventService
from app.services.whatsapp_client import (
    WhatsAppCloudClient,
    WhatsAppCloudClientError,
    sanitize_whatsapp_error,
)
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.whatsapp_flow_compiler import WhatsAppFlowCompiler
from app.services.whatsapp_flow_context_adapter import blank_builder, builder_from_context_schema


class WhatsAppFlowNotFoundError(ValueError):
    pass


class WhatsAppFlowConflictError(ValueError):
    pass


class WhatsAppFlowValidationError(ValueError):
    pass


class WhatsAppFlowProviderError(RuntimeError):
    pass


COMPATIBLE_BINDINGS = {
    "text_input": {"text"},
    "text_area": {"textarea", "text"},
    "email_input": {"email"},
    "phone_input": {"phone"},
    "number_input": {"integer"},
    "dropdown": {"select"},
    "radio": {"select"},
    "checkbox": {"checkbox"},
    "date": {"date"},
}


class WhatsAppFlowService:
    provider = "whatsapp_cloud"

    def __init__(self, db: Session, client: WhatsAppCloudClient | None = None) -> None:
        self.db = db
        self.client = client or WhatsAppCloudClient()
        self.compiler = WhatsAppFlowCompiler()
        self.events = IntegrationEventService(db)

    def list_flows(self, tenant_id: str) -> list[WhatsAppFlowResponse]:
        rows = self.db.scalars(
            select(TenantWhatsAppFlow)
            .where(TenantWhatsAppFlow.tenant_id == tenant_id)
            .order_by(TenantWhatsAppFlow.updated_at.desc())
        ).all()
        return [self.response(row) for row in rows]

    def get_owned(self, tenant_id: str, flow_id: str) -> TenantWhatsAppFlow:
        flow = self.db.scalar(
            select(TenantWhatsAppFlow).where(
                TenantWhatsAppFlow.id == flow_id,
                TenantWhatsAppFlow.tenant_id == tenant_id,
            )
        )
        if flow is None:
            raise WhatsAppFlowNotFoundError("WhatsApp Flow not found.")
        return flow

    def create_draft(
        self,
        tenant_id: str,
        body: WhatsAppFlowCreateRequest,
        created_by_user_id: str | None,
    ) -> WhatsAppFlowResponse:
        if self.db.scalar(
            select(TenantWhatsAppFlow.id).where(
                TenantWhatsAppFlow.tenant_id == tenant_id,
                TenantWhatsAppFlow.flow_key == body.flow_key,
            )
        ):
            raise WhatsAppFlowConflictError("A Flow with this key already exists.")
        snapshot = None
        if body.source_mode == "context_schema":
            schema = self._get_context_schema(tenant_id, body.context_schema_id or "")
            builder, snapshot = builder_from_context_schema(schema)
            try:
                builder = FlowBuilder.model_validate(builder).model_dump(mode="json")
            except ValueError as exc:
                raise WhatsAppFlowValidationError(str(exc)) from exc
        else:
            builder = body.builder.model_dump(mode="json") if body.builder else blank_builder()
        self._validate_bindings(builder, snapshot)
        flow = TenantWhatsAppFlow(
            tenant_id=tenant_id,
            flow_key=body.flow_key,
            version=1,
            name=body.name,
            categories_json=list(body.categories),
            source_mode=body.source_mode,
            context_schema_id=body.context_schema_id,
            context_schema_snapshot_json=snapshot,
            status="draft",
            builder_schema_version=1,
            builder_json=builder,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(flow)
        self.db.commit()
        self.db.refresh(flow)
        self._event(flow, "whatsapp_flow_created")
        return self.response(flow)

    def update_draft(
        self,
        tenant_id: str,
        flow_id: str,
        body: WhatsAppFlowUpdateRequest,
    ) -> WhatsAppFlowResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status in {"published", "deprecated"}:
            raise WhatsAppFlowConflictError("Published or deprecated Flows are immutable.")
        changed = False
        if body.name is not None:
            flow.name = body.name
            changed = True
        if body.categories is not None:
            flow.categories_json = list(body.categories)
            changed = True
        if body.builder is not None:
            builder = body.builder.model_dump(mode="json")
            self._validate_bindings(builder, flow.context_schema_snapshot_json)
            flow.builder_json = builder
            flow.compiled_flow_json = None
            flow.compiled_hash = None
            changed = True
        if changed:
            flow.status = "draft"
            flow.validation_errors_json = []
            self.db.commit()
            self.db.refresh(flow)
            self._event(flow, "whatsapp_flow_updated")
        return self.response(flow)

    def delete_draft(self, tenant_id: str, flow_id: str) -> None:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status in {"published", "deprecated"}:
            raise WhatsAppFlowConflictError("Published or deprecated Flows cannot be deleted.")
        if flow.provider_flow_id:
            _, client_config = WhatsAppConfigService(self.db, self.client).get_active_client_config(tenant_id)
            self._provider_call(flow, "whatsapp_flow_delete_failed", self.client.delete_flow, client_config, flow_id=flow.provider_flow_id)
        resource_id = flow.id
        self.db.delete(flow)
        self.db.commit()
        self.events.record_event(
            tenant_id=tenant_id,
            provider=self.provider,
            event_type="whatsapp_flow_deleted",
            status="success",
            resource_type="tenant_whatsapp_flow",
            resource_id=resource_id,
        )

    def compile(self, tenant_id: str, flow_id: str) -> WhatsAppFlowCompileResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status in {"published", "deprecated"}:
            raise WhatsAppFlowConflictError("Published or deprecated Flows are immutable.")
        self._validate_bindings(flow.builder_json, flow.context_schema_snapshot_json)
        try:
            compiled, compiled_hash = self.compiler.compile(flow.builder_json)
        except ValueError as exc:
            raise WhatsAppFlowValidationError(str(exc)) from exc
        flow.compiled_flow_json = compiled
        flow.compiled_hash = compiled_hash
        self.db.commit()
        self._event(flow, "whatsapp_flow_compiled", metadata={"compiled_hash": compiled_hash})
        return WhatsAppFlowCompileResponse(compiled_flow_json=compiled, compiled_hash=compiled_hash)

    def sync_meta(self, tenant_id: str, flow_id: str) -> WhatsAppFlowResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status in {"published", "deprecated"}:
            raise WhatsAppFlowConflictError("Published or deprecated Flows cannot be synchronized as drafts.")
        self.compile(tenant_id, flow_id)
        flow = self.get_owned(tenant_id, flow_id)
        config, client_config = WhatsAppConfigService(self.db, self.client).get_active_client_config(tenant_id)
        waba_id = (config.business_account_id or "").strip()
        if not waba_id:
            raise WhatsAppFlowValidationError("Business Account ID / WABA ID is required.")
        if not flow.provider_flow_id:
            clone_flow_id = None
            if flow.parent_flow_id:
                parent = self.get_owned(tenant_id, flow.parent_flow_id)
                clone_flow_id = parent.provider_flow_id
            payload = self._provider_call(
                flow,
                "whatsapp_flow_meta_create_failed",
                self.client.create_flow,
                client_config,
                waba_id=waba_id,
                name=flow.name,
                categories=flow.categories_json,
                clone_flow_id=clone_flow_id,
            )
            provider_flow_id = str(payload.get("id") or "").strip()
            if not provider_flow_id:
                raise WhatsAppFlowProviderError("Meta did not return a Flow ID.")
            flow.provider_flow_id = provider_flow_id
            flow.meta_status = "DRAFT"
            self.db.commit()
            self._event(flow, "whatsapp_flow_meta_created")
        else:
            self._provider_call(
                flow,
                "whatsapp_flow_meta_update_failed",
                self.client.update_flow_metadata,
                client_config,
                flow_id=flow.provider_flow_id,
                name=flow.name,
                categories=flow.categories_json,
            )
        payload = self._provider_call(
            flow,
            "whatsapp_flow_meta_validation_failed",
            self.client.upload_flow_json,
            client_config,
            flow_id=flow.provider_flow_id,
            flow_json=flow.compiled_flow_json or {},
        )
        errors = self._validation_errors(payload.get("validation_errors"))
        flow.validation_errors_json = errors
        flow.last_synced_at = datetime.now(timezone.utc)
        if errors:
            flow.status = "error"
            flow.synced_hash = None
        else:
            flow.status = "synced"
            flow.synced_hash = flow.compiled_hash
        self.db.commit()
        self.db.refresh(flow)
        self._event(
            flow,
            "whatsapp_flow_meta_validation_failed" if errors else "whatsapp_flow_meta_synced",
            status="failed" if errors else "success",
            metadata={"validation_error_count": len(errors)},
        )
        return self.response(flow)

    def sync_status(self, tenant_id: str, flow_id: str) -> WhatsAppFlowResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if not flow.provider_flow_id:
            raise WhatsAppFlowValidationError("Flow has not been created in Meta yet.")
        _, client_config = WhatsAppConfigService(self.db, self.client).get_active_client_config(tenant_id)
        payload = self._provider_call(
            flow,
            "whatsapp_flow_status_sync_failed",
            self.client.get_flow,
            client_config,
            flow_id=flow.provider_flow_id,
        )
        meta_status = str(payload.get("status") or "").upper()
        flow.meta_status = meta_status or flow.meta_status
        flow.validation_errors_json = self._validation_errors(payload.get("validation_errors"))
        flow.last_synced_at = datetime.now(timezone.utc)
        if meta_status == "PUBLISHED":
            flow.status = "published"
            flow.published_at = flow.published_at or datetime.now(timezone.utc)
        elif meta_status == "DEPRECATED":
            flow.status = "deprecated"
            flow.deprecated_at = flow.deprecated_at or datetime.now(timezone.utc)
        elif flow.validation_errors_json:
            flow.status = "error"
        elif meta_status == "DRAFT" and flow.synced_hash == flow.compiled_hash:
            flow.status = "synced"
        self.db.commit()
        self.db.refresh(flow)
        self._event(flow, "whatsapp_flow_status_synced", metadata={"meta_status": meta_status})
        return self.response(flow)

    def publish(self, tenant_id: str, flow_id: str) -> WhatsAppFlowResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status in {"published", "deprecated"}:
            raise WhatsAppFlowConflictError("Flow is already immutable.")
        if flow.status != "synced" or not flow.compiled_hash or flow.synced_hash != flow.compiled_hash or not flow.provider_flow_id:
            self.sync_meta(tenant_id, flow_id)
            flow = self.get_owned(tenant_id, flow_id)
        if flow.validation_errors_json:
            raise WhatsAppFlowConflictError("Meta validation errors must be resolved before publishing.")
        _, client_config = WhatsAppConfigService(self.db, self.client).get_active_client_config(tenant_id)
        payload = self._provider_call(
            flow,
            "whatsapp_flow_publish_failed",
            self.client.publish_flow,
            client_config,
            flow_id=flow.provider_flow_id,
        )
        if payload.get("success") is not True:
            raise WhatsAppFlowProviderError("Meta did not confirm Flow publication.")
        flow.status = "published"
        flow.meta_status = "PUBLISHED"
        flow.published_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(flow)
        self._event(flow, "whatsapp_flow_published")
        return self.response(flow)

    def clone_published(
        self,
        tenant_id: str,
        flow_id: str,
        created_by_user_id: str | None,
    ) -> WhatsAppFlowResponse:
        source = self.get_owned(tenant_id, flow_id)
        if source.status != "published":
            raise WhatsAppFlowConflictError("Only published Flows can create a new version.")
        latest_version = self.db.scalar(
            select(func.max(TenantWhatsAppFlow.version)).where(
                TenantWhatsAppFlow.tenant_id == tenant_id,
                TenantWhatsAppFlow.flow_key == source.flow_key,
            )
        ) or 0
        clone = TenantWhatsAppFlow(
            tenant_id=tenant_id,
            flow_key=source.flow_key,
            version=latest_version + 1,
            parent_flow_id=source.id,
            name=source.name,
            categories_json=list(source.categories_json),
            source_mode=source.source_mode,
            context_schema_id=source.context_schema_id,
            context_schema_snapshot_json=source.context_schema_snapshot_json,
            status="draft",
            builder_schema_version=source.builder_schema_version,
            builder_json=source.builder_json,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(clone)
        self.db.commit()
        self.db.refresh(clone)
        self._event(clone, "whatsapp_flow_cloned", metadata={"source_version": source.version})
        return self.response(clone)

    def deprecate(self, tenant_id: str, flow_id: str) -> WhatsAppFlowResponse:
        flow = self.get_owned(tenant_id, flow_id)
        if flow.status != "published" or not flow.provider_flow_id:
            raise WhatsAppFlowConflictError("Only published Meta Flows can be deprecated.")
        _, client_config = WhatsAppConfigService(self.db, self.client).get_active_client_config(tenant_id)
        payload = self._provider_call(
            flow,
            "whatsapp_flow_deprecate_failed",
            self.client.deprecate_flow,
            client_config,
            flow_id=flow.provider_flow_id,
        )
        if payload.get("success") is not True:
            raise WhatsAppFlowProviderError("Meta did not confirm Flow deprecation.")
        flow.status = "deprecated"
        flow.meta_status = "DEPRECATED"
        flow.deprecated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(flow)
        self._event(flow, "whatsapp_flow_deprecated")
        return self.response(flow)

    def response(self, flow: TenantWhatsAppFlow) -> WhatsAppFlowResponse:
        return WhatsAppFlowResponse(
            id=flow.id,
            flow_key=flow.flow_key,
            version=flow.version,
            parent_flow_id=flow.parent_flow_id,
            name=flow.name,
            categories=flow.categories_json,
            source_mode=flow.source_mode,
            context_schema_id=flow.context_schema_id,
            context_schema_snapshot=flow.context_schema_snapshot_json,
            status=flow.status,
            meta_status=flow.meta_status,
            provider_flow_id=flow.provider_flow_id,
            builder_schema_version=flow.builder_schema_version,
            builder=flow.builder_json,
            compiled_flow_json=flow.compiled_flow_json,
            compiled_hash=flow.compiled_hash,
            validation_errors=flow.validation_errors_json or [],
            last_synced_at=flow.last_synced_at,
            published_at=flow.published_at,
            deprecated_at=flow.deprecated_at,
            created_at=flow.created_at,
            updated_at=flow.updated_at,
        )

    def _get_context_schema(self, tenant_id: str, schema_id: str) -> TenantVoiceContextSchema:
        schema = self.db.scalar(
            select(TenantVoiceContextSchema).where(
                TenantVoiceContextSchema.id == schema_id,
                TenantVoiceContextSchema.tenant_id == tenant_id,
            )
        )
        if schema is None:
            raise WhatsAppFlowNotFoundError("Context Schema not found.")
        return schema

    def _validate_bindings(self, builder: dict, snapshot: dict | None) -> None:
        bound = [
            component
            for screen in builder.get("screens", [])
            for component in screen.get("components", [])
            if component.get("binding")
        ]
        if not bound:
            return
        fields = {field["key"]: field for field in (snapshot or {}).get("fields", [])}
        for component in bound:
            key = component["binding"].get("context_field_key")
            field = fields.get(key)
            if field is None:
                raise WhatsAppFlowValidationError(f"Context binding {key} does not exist in the schema snapshot.")
            if field["field_type"] not in COMPATIBLE_BINDINGS.get(component.get("type"), set()):
                raise WhatsAppFlowValidationError(f"Context binding {key} is incompatible with {component.get('type')}.")

    @staticmethod
    def _validation_errors(raw: Any) -> list[dict]:
        if not isinstance(raw, list):
            return []
        errors = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            parsed = MetaFlowValidationError.model_validate(item).model_dump()
            parsed["message"] = sanitize_whatsapp_error(parsed.get("message"))
            errors.append(parsed)
        return errors

    def _provider_call(self, flow: TenantWhatsAppFlow, failed_event: str, method, *args, **kwargs) -> dict:
        try:
            return method(*args, **kwargs)
        except (ValueError, WhatsAppCloudClientError) as exc:
            message = sanitize_whatsapp_error(str(exc)) or "WhatsApp Flow provider request failed."
            self._event(flow, failed_event, status="failed", message=message)
            raise WhatsAppFlowProviderError(message) from exc

    def _event(
        self,
        flow: TenantWhatsAppFlow,
        event_type: str,
        *,
        status: str = "success",
        message: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.events.record_event(
            tenant_id=flow.tenant_id,
            provider=self.provider,
            event_type=event_type,
            status=status,
            resource_type="tenant_whatsapp_flow",
            resource_id=flow.id,
            message=message,
            metadata={"flow_key": flow.flow_key, "version": flow.version, **(metadata or {})},
        )
