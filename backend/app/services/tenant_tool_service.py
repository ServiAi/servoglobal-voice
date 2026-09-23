from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.tool_namespace import InvalidToolKeyError, validate_custom_key
from app.models.agents import TenantAgentVersion
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.schemas.session_context import SessionContextV1
from app.schemas.tools_custom import (
    CredentialMaskedResponse,
    CustomToolCreateRequest,
    CustomToolResponse,
    CustomToolTestResponse,
    CustomToolUpdateRequest,
    is_sensitive_header_name,
)
from app.services.custom_http_tool_executor import CustomHttpToolExecutor
from app.services.tenant_feature_service import CUSTOM_HTTP_TOOLS, TenantFeatureService
from app.services.tenant_tool_credential_service import TenantToolCredentialService, TenantToolNotFoundError


class TenantToolError(ValueError):
    pass


class DuplicateToolKeyError(TenantToolError):
    pass


class ToolInUseError(TenantToolError):
    pass


class TenantToolService:
    """CRUD + lifecycle for tenant-authored Custom HTTP Tools. Every method
    is feature-gated on CUSTOM_HTTP_TOOLS and every query filters by
    tenant_id -- a wrong/foreign tool_id 404s (TenantToolNotFoundError)
    rather than ever confirming it exists for another tenant."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.feature_service = TenantFeatureService(db)
        self.credential_service = TenantToolCredentialService(db)

    def list_tools(self, tenant_id: str) -> list[CustomToolResponse]:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tools = self.db.scalars(
            select(TenantTool).where(TenantTool.tenant_id == tenant_id).order_by(TenantTool.created_at)
        ).all()
        return [self._response(tool) for tool in tools]

    def get_tool(self, tenant_id: str, tool_id: str) -> CustomToolResponse:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        return self._response(self._get_tool_or_raise(tenant_id, tool_id))

    def create_tool(
        self, tenant_id: str, user_id: str | None, payload: CustomToolCreateRequest
    ) -> CustomToolResponse:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        try:
            validate_custom_key(payload.key)
        except InvalidToolKeyError as exc:
            raise TenantToolError(str(exc)) from exc
        if payload.auth_type == "api_key" and not payload.api_key_header_name:
            raise TenantToolError("api_key_header_name is required for auth_type=api_key.")
        self.credential_service.validate_credential(
            auth_type=payload.auth_type,
            secrets=payload.secrets,
            api_key_header_name=payload.api_key_header_name,
            allow_missing_secrets=True,
        )

        tool = TenantTool(
            tenant_id=tenant_id,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            status="disabled",
            created_by_user_id=user_id,
        )
        self.db.add(tool)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateToolKeyError(f"A tool with key '{payload.key}' already exists.") from exc

        self.db.add(
            TenantHttpToolConfig(
                tenant_id=tenant_id,
                tenant_tool_id=tool.id,
                method=payload.method,
                base_url=payload.base_url,
                path_template=payload.path_template,
                timeout_ms=payload.timeout_ms,
                headers_json=payload.headers,
                path_mapping_json=payload.path_mapping,
                query_mapping_json=payload.query_mapping,
                body_mapping_json=payload.body_mapping,
                input_schema_json=payload.input_schema,
                response_mapping_json=payload.response_mapping,
            )
        )
        if payload.auth_type != "none":
            if payload.secrets:
                self.credential_service.set_credential(
                    tenant_id,
                    tool.id,
                    auth_type=payload.auth_type,
                    secrets=payload.secrets,
                    api_key_header_name=payload.api_key_header_name,
                    actor_user_id=user_id,
                )
            else:
                # Auth type chosen now, secret to be supplied later via
                # update_tool -- activate_tool blocks activation until then.
                self.credential_service.declare_auth_type(
                    tenant_id,
                    tool.id,
                    auth_type=payload.auth_type,
                    api_key_header_name=payload.api_key_header_name,
                    actor_user_id=user_id,
                )
        else:
            self.db.commit()
        self.db.refresh(tool)
        return self._response(tool)

    def update_tool(
        self, tenant_id: str, tool_id: str, payload: CustomToolUpdateRequest, *, actor_user_id: str | None = None
    ) -> CustomToolResponse:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tool = self._get_tool_or_raise(tenant_id, tool_id)
        config = self._get_config_or_raise(tenant_id, tool.id)

        current_credential = None
        if payload.auth_type is not None:
            current_credential = self.credential_service.get_masked(tenant_id, tool.id)
            effective_header = (
                payload.api_key_header_name
                or (current_credential.api_key_header_name if payload.auth_type == current_credential.auth_type else None)
            )
            self.credential_service.validate_credential(
                auth_type=payload.auth_type,
                secrets=payload.secrets,
                api_key_header_name=effective_header,
                allow_missing_secrets=True,
            )

        if payload.name is not None:
            tool.name = payload.name
        if payload.description is not None:
            tool.description = payload.description
        if payload.method is not None:
            config.method = payload.method
        if payload.base_url is not None:
            config.base_url = payload.base_url
        if payload.path_template is not None:
            config.path_template = payload.path_template
        if payload.timeout_ms is not None:
            config.timeout_ms = payload.timeout_ms
        if payload.headers is not None:
            config.headers_json = payload.headers
        if payload.path_mapping is not None:
            config.path_mapping_json = payload.path_mapping
        if payload.query_mapping is not None:
            config.query_mapping_json = payload.query_mapping
        if payload.body_mapping is not None:
            config.body_mapping_json = payload.body_mapping
        if payload.input_schema is not None:
            config.input_schema_json = payload.input_schema
        if payload.response_mapping is not None:
            config.response_mapping_json = payload.response_mapping
        if payload.auth_type is not None:
            if payload.secrets:
                self.credential_service.set_credential(
                    tenant_id,
                    tool.id,
                    auth_type=payload.auth_type,
                    secrets=payload.secrets,
                    api_key_header_name=payload.api_key_header_name,
                    actor_user_id=actor_user_id,
                )
            else:
                assert current_credential is not None
                if payload.auth_type != current_credential.auth_type:
                    # Switching auth mechanism without a new secret --
                    # declare the new type; the old secret (for the old
                    # mechanism) is no longer meaningful either way.
                    self.credential_service.declare_auth_type(
                        tenant_id,
                        tool.id,
                        auth_type=payload.auth_type,
                        api_key_header_name=payload.api_key_header_name,
                        actor_user_id=actor_user_id,
                    )
                elif (
                    payload.auth_type == "api_key"
                    and payload.api_key_header_name is not None
                    and payload.api_key_header_name != current_credential.api_key_header_name
                ):
                    self.credential_service.update_api_key_header_name(
                        tenant_id, tool.id, payload.api_key_header_name or ""
                    )
                else:
                    self.db.commit()
        else:
            self.db.commit()
        self.db.refresh(tool)
        return self._response(tool)

    def activate_tool(self, tenant_id: str, tool_id: str) -> CustomToolResponse:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tool = self._get_tool_or_raise(tenant_id, tool_id)
        if not self.credential_service.is_configured_or_not_required(tenant_id, tool.id):
            raise TenantToolError("tool_credential_not_configured")
        tool.status = "active"
        self.db.commit()
        self.db.refresh(tool)
        return self._response(tool)

    def disable_tool(self, tenant_id: str, tool_id: str) -> CustomToolResponse:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tool = self._get_tool_or_raise(tenant_id, tool_id)
        tool.status = "disabled"
        self.db.commit()
        self.db.refresh(tool)
        return self._response(tool)

    def delete_tool(self, tenant_id: str, tool_id: str) -> None:
        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tool = self._get_tool_or_raise(tenant_id, tool_id)
        if self._is_bound_to_a_published_agent(tenant_id, tool.key):
            raise ToolInUseError(f"Tool '{tool.key}' is bound to a published agent version.")
        self.db.delete(tool)
        self.db.commit()

    def test_tool(self, tenant_id: str, tool_id: str, arguments: dict[str, Any]) -> CustomToolTestResponse:
        import time

        self.feature_service.require_enabled(tenant_id, CUSTOM_HTTP_TOOLS)
        tool = self._get_tool_or_raise(tenant_id, tool_id)
        config = self._get_config_or_raise(tenant_id, tool.id)

        from app.services.tool_dispatch_service import ToolArgumentError, ToolExecutionError

        captured_status: list[int] = []
        started_at = time.monotonic()
        try:
            result = CustomHttpToolExecutor(self.db).execute(
                tenant_id=tenant_id,
                tenant_tool=tool,
                config=config,
                arguments=arguments,
                context=SessionContextV1(),
                binding_config={},
                on_response_status=captured_status.append,
            )
        except (ToolArgumentError, ToolExecutionError) as exc:
            return CustomToolTestResponse(
                success=False,
                status_code=captured_status[0] if captured_status else None,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                error_code=str(exc),
            )
        return CustomToolTestResponse(
            success=True,
            status_code=captured_status[0] if captured_status else None,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            mapped_result=result,
        )

    def _is_bound_to_a_published_agent(self, tenant_id: str, key: str) -> bool:
        published_versions = self.db.scalars(
            select(TenantAgentVersion).where(
                TenantAgentVersion.tenant_id == tenant_id, TenantAgentVersion.status == "published"
            )
        ).all()
        for version in published_versions:
            bindings = (version.runtime_binding_json or {}).get("tools", [])
            if any(isinstance(b, dict) and b.get("key") == key for b in bindings):
                return True
        return False

    def _get_tool_or_raise(self, tenant_id: str, tool_id: str) -> TenantTool:
        tool = self.db.scalar(
            select(TenantTool).where(TenantTool.id == tool_id, TenantTool.tenant_id == tenant_id)
        )
        if tool is None:
            raise TenantToolNotFoundError(tool_id)
        return tool

    def _get_config_or_raise(self, tenant_id: str, tenant_tool_id: str) -> TenantHttpToolConfig:
        config = self.db.scalar(
            select(TenantHttpToolConfig).where(
                TenantHttpToolConfig.tenant_id == tenant_id,
                TenantHttpToolConfig.tenant_tool_id == tenant_tool_id,
            )
        )
        if config is None:
            raise TenantToolNotFoundError(tenant_tool_id)
        return config

    def _response(self, tool: TenantTool) -> CustomToolResponse:
        config = self._get_config_or_raise(tool.tenant_id, tool.id)
        masked = self.credential_service.get_masked(tool.tenant_id, tool.id)
        return CustomToolResponse(
            id=tool.id,
            tenant_id=tool.tenant_id,
            key=tool.key,
            name=tool.name,
            description=tool.description,
            status=tool.status,
            method=config.method,
            base_url=config.base_url,
            path_template=config.path_template,
            timeout_ms=config.timeout_ms,
            headers={
                key: value
                for key, value in (config.headers_json or {}).items()
                if not is_sensitive_header_name(key)
            },
            path_mapping=config.path_mapping_json,
            query_mapping=config.query_mapping_json,
            body_mapping=config.body_mapping_json,
            input_schema=config.input_schema_json,
            response_mapping=config.response_mapping_json,
            credential=CredentialMaskedResponse(
                auth_type=masked.auth_type,
                configured=masked.configured,
                api_key_header_name=masked.api_key_header_name,
                masked_fields=masked.masked_fields,
            ),
            created_at=tool.created_at,
            updated_at=tool.updated_at,
        )
