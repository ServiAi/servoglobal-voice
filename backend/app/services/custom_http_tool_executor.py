from __future__ import annotations

import base64
import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tool_http_limits import DEFAULT_TIMEOUT_MS
from app.domain.tool_mapping import (
    MappingPathError,
    build_path,
    build_request_values,
    extract_response_values,
)
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.schemas.session_context import SessionContextV1
from app.schemas.tools_custom import is_sensitive_header_name
from app.services.tenant_tool_credential_service import ResolvedCredential, TenantToolCredentialService
from app.services.tool_http_safety import (
    ResponseTooLargeError,
    SafeHttpClient,
    UnsafeUrlError,
    UpstreamRequestError,
)

# Tenant-configured static headers can never override these -- Authorization
# comes exclusively from the resolved credential, and the rest are either
# connection-level (never meaningful to set by hand) or would let a header
# smuggle a second request.
_BLOCKED_HEADER_NAMES = frozenset(
    {
        "host",
        "authorization",
        "proxy-authorization",
        "connection",
        "content-length",
        "transfer-encoding",
        "cookie",
        "set-cookie",
    }
)

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_REQUIRED_CREDENTIAL_FIELDS = {
    "none": frozenset(),
    "bearer": frozenset({"token"}),
    "api_key": frozenset({"api_key"}),
    "basic": frozenset({"username", "password"}),
}


class CustomHttpToolExecutor:
    """Executes a single Custom HTTP Tool call: validates arguments,
    resolves the tenant's credential, builds the request from declarative
    mappings, calls SafeHttpClient, and maps the response. Raises
    ToolArgumentError/ToolExecutionError (imported lazily to avoid a
    circular import with tool_dispatch_service) with stable, non-leaking
    messages -- the raw endpoint URL and credential never appear in any
    exception message or return value.
    """

    def __init__(self, db: Session, *, http_client: SafeHttpClient | None = None) -> None:
        self.db = db
        self._http_client = http_client or SafeHttpClient()

    def execute(
        self,
        *,
        tenant_id: str,
        tenant_tool: TenantTool,
        config: TenantHttpToolConfig,
        arguments: dict[str, Any],
        context: SessionContextV1,
        binding_config: dict[str, Any],
        on_response_status: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        from app.services.tool_dispatch_service import ToolArgumentError, ToolDispatchService, ToolExecutionError

        ToolDispatchService._validate_arguments(config.input_schema_json, arguments)

        credential = TenantToolCredentialService(self.db).resolve_for_execution(tenant_id, tenant_tool.id)
        if set(credential.secrets) != _REQUIRED_CREDENTIAL_FIELDS.get(credential.auth_type, frozenset()):
            raise ToolExecutionError("tool_credential_not_configured")
        context_dict = context.model_dump()

        try:
            path = build_path(
                config.path_template,
                config.path_mapping_json,
                args=arguments,
                context=context_dict,
                binding_config=binding_config,
            )
            query_values = build_request_values(
                config.query_mapping_json, args=arguments, context=context_dict, binding_config=binding_config
            )
            body_values = (
                build_request_values(
                    config.body_mapping_json, args=arguments, context=context_dict, binding_config=binding_config
                )
                if config.method in _BODY_METHODS
                else {}
            )
        except MappingPathError as exc:
            raise ToolArgumentError(str(exc)) from exc

        headers = self._build_headers(config.headers_json, credential)
        url = f"{config.base_url.rstrip('/')}{path}"

        try:
            response = self._http_client.request(
                method=config.method,
                url=url,
                headers=headers,
                params=query_values or None,
                json_body=body_values or None,
                timeout_ms=config.timeout_ms or DEFAULT_TIMEOUT_MS,
                allow_http=settings.CUSTOM_TOOLS_ALLOW_HTTP,
            )
        except UnsafeUrlError as exc:
            raise ToolExecutionError(f"custom_tool_unsafe_target:{exc.reason}") from exc
        except ResponseTooLargeError as exc:
            raise ToolExecutionError("custom_tool_response_too_large") from exc
        except UpstreamRequestError as exc:
            raise ToolExecutionError("custom_tool_upstream_error") from exc

        if on_response_status is not None:
            on_response_status(response.status_code)

        if response.status_code >= 400:
            raise ToolExecutionError(f"custom_tool_upstream_status:{response.status_code}")

        if response.content_type == "application/json":
            try:
                response_body: Any = json.loads(response.body_bytes) if response.body_bytes else {}
            except ValueError as exc:
                raise ToolExecutionError("custom_tool_invalid_json_response") from exc
        else:
            response_body = response.body_bytes.decode("utf-8", errors="replace")

        if not config.response_mapping_json:
            return response_body if isinstance(response_body, dict) else {"response": response_body}
        try:
            return extract_response_values(config.response_mapping_json, response_body)
        except MappingPathError as exc:
            raise ToolExecutionError(f"custom_tool_response_mapping_error:{exc}") from exc

    def _build_headers(self, headers_json: dict[str, str], credential: ResolvedCredential) -> dict[str, str]:
        headers = {
            key: value
            for key, value in (headers_json or {}).items()
            if key.lower() not in _BLOCKED_HEADER_NAMES and not is_sensitive_header_name(key)
        }
        if credential.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {credential.secrets['token']}"
        elif credential.auth_type == "api_key":
            headers[credential.api_key_header_name or "X-API-Key"] = credential.secrets["api_key"]
        elif credential.auth_type == "basic":
            raw = f"{credential.secrets['username']}:{credential.secrets['password']}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
        return headers
