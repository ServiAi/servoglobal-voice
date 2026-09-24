from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.platform_tool_invocation import PlatformToolInvocation
from app.domain.resolved_tool import ResolvedToolDefinition
from app.domain.tool_mapping import MappingPathError, resolve_path
from app.domain.tool_schema import ToolSchemaError, validate_arguments_against_schema
from app.models.integrations import TenantWhatsAppTemplate
from app.schemas.session_context import SessionContextV1
from app.services.whatsapp_template_service import WhatsAppTemplateService

_WHATSAPP_CONTRACT_VERSION = 2
_WHATSAPP_RECIPIENT_STRATEGIES = frozenset({"contact_then_caller", "contact", "caller"})
_WHATSAPP_VARIABLE_SOURCES = frozenset({"llm", "context", "fixed"})
_WHATSAPP_LLM_VARIABLE_TYPES = frozenset({"string", "number", "integer", "boolean"})

# Explicit allowlist of SessionContextV1 paths a WhatsApp variable may read
# with source=context -- mirrors app.schemas.session_context's shape
# one-to-one, never arbitrary object traversal. Kept local to this service
# (rather than on SessionContextV1 itself) since it is a Platform Tool
# Contract concern, not a property of the context schema itself.
_WHATSAPP_ALLOWED_CONTEXT_PATHS = frozenset(
    {
        "caller.phone",
        "contact.id",
        "contact.name",
        "contact.phone",
        "contact.email",
        "lead.id",
        "lead.status",
        "lead.stage",
        "campaign.name",
    }
)


class PlatformToolContractError(ValueError):
    """Raised by every validation/resolution method on this service. `code`
    is a stable, caller-facing identifier (see the module docstring's list)
    -- callers (AgentService, ToolDispatchService) turn it into the
    HTTP-detail / AgentValidationError shape their own layer already uses,
    the same way ToolRegistryValidationError's `tool_not_found:{key}`
    strings are consumed today."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class WhatsAppSendPlan:
    """What PlatformToolContractService.resolve_whatsapp_send hands to
    ToolDispatchService's whatsapp.send_message handler -- already fully
    resolved (recipient, template, variables), so the handler only calls
    WhatsAppMessageService.send_template_notification with it."""

    to_phone: str
    template_key: str
    variables: dict[str, str]
    lead_id: str | None
    contact_id: str | None


class PlatformToolContractService:
    """Single seam for the three-source Platform Tool contract (LLM args /
    SessionContextV1 / AgentToolBinding.config). AgentService (draft save +
    publish preflight), AgentCompilerService (effective LLM schema) and
    ToolDispatchService (live invocation) all call through here instead of
    each re-implementing WhatsApp's binding rules -- see the Sprint 3
    Platform Tools refactor plan for why.

    Today only whatsapp.send_message has a real binding_config_schema;
    every other available Platform Tool (calendar.*, crm.create_lead) has
    an empty one and every method below is a no-op passthrough for them.
    Custom HTTP Tools never go through this service at all -- they keep
    their own contract (app.domain.tool_mapping + CustomHttpToolExecutor).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- draft save / publish preflight -----------------------------------

    def validate_binding_config(self, tenant_id: str, tool: ResolvedToolDefinition, config: dict[str, Any]) -> None:
        if tool.key == "whatsapp.send_message":
            self._validate_whatsapp_binding_config(tenant_id, config)

    # -- agent compiler -----------------------------------------------------

    def compile_llm_schema(self, tool: ResolvedToolDefinition, config: dict[str, Any]) -> dict[str, Any]:
        if tool.key == "whatsapp.send_message":
            return self._compile_whatsapp_llm_schema(config)
        return tool.input_schema

    # -- tool dispatch --------------------------------------------------

    def validate_context(self, tool: ResolvedToolDefinition, config: dict[str, Any], context: SessionContextV1) -> None:
        context_dump = context.model_dump(mode="json")
        for requirement in tool.context_requirements:
            if not requirement.required:
                continue
            if not self._path_has_value(context_dump, requirement.path):
                raise PlatformToolContractError(
                    "tool_context_required", f"{tool.key} requires session context '{requirement.path}'."
                )
        if tool.key == "whatsapp.send_message":
            strategy = (config.get("recipient") or {}).get("strategy") if isinstance(config, dict) else None
            self._resolve_whatsapp_recipient(strategy, context_dump)

    def validate_llm_arguments(self, tool: ResolvedToolDefinition, config: dict[str, Any], arguments: dict[str, Any]) -> None:
        schema = self.compile_llm_schema(tool, config)
        try:
            validate_arguments_against_schema(schema, arguments)
        except ToolSchemaError as exc:
            raise PlatformToolContractError("tool_argument_invalid", str(exc)) from exc

    def build_invocation(
        self, *, llm_args: dict[str, Any], context: SessionContextV1, config: dict[str, Any]
    ) -> PlatformToolInvocation:
        return PlatformToolInvocation(llm_args=llm_args, context=context, config=config)

    def resolve_whatsapp_send(self, tenant_id: str, invocation: PlatformToolInvocation) -> WhatsAppSendPlan:
        """Turns a validated whatsapp.send_message invocation into concrete
        to_phone/template_key/variables -- the payload the LLM must never be
        allowed to assemble itself. Re-validates contract_version and the
        template's tenant/approved status again here (not just at publish
        time): the template could have been unsynced/unapproved, or the
        binding could be a pre-V2 published version, since the agent was
        last published."""
        config = invocation.config if isinstance(invocation.config, dict) else {}
        if config.get("contract_version") != _WHATSAPP_CONTRACT_VERSION:
            raise PlatformToolContractError(
                "whatsapp_legacy_binding_unsupported",
                "This agent's whatsapp.send_message binding predates contract_version=2; "
                "republish the agent after configuring the WhatsApp tool (template, recipient, variables).",
            )
        template_key = str(config.get("template_key") or "")
        template = self._get_approved_template(tenant_id, template_key)
        context_dump = invocation.context.model_dump(mode="json")
        strategy = (config.get("recipient") or {}).get("strategy")
        to_phone = self._resolve_whatsapp_recipient(strategy, context_dump)

        required_keys = WhatsAppTemplateService(self.db).get_approved_parameter_keys(template)
        variables_config = config.get("variables") if isinstance(config.get("variables"), dict) else {}
        variables: dict[str, str] = {}
        for key in required_keys:
            spec = variables_config.get(key)
            if not isinstance(spec, dict):
                raise PlatformToolContractError("whatsapp_variable_mapping_incomplete", f"No mapping for template variable '{key}'.")
            variables[key] = self._resolve_whatsapp_variable(key, spec, invocation, context_dump)

        contact = context_dump.get("contact") or {}
        lead = context_dump.get("lead") or {}
        return WhatsAppSendPlan(
            to_phone=to_phone,
            template_key=template.template_key,
            variables=variables,
            lead_id=lead.get("id"),
            contact_id=contact.get("id"),
        )

    # -- whatsapp internals -------------------------------------------------

    def _validate_whatsapp_binding_config(self, tenant_id: str, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise PlatformToolContractError("tool_binding_config_invalid", "whatsapp.send_message config must be an object.")
        if config.get("contract_version") != _WHATSAPP_CONTRACT_VERSION:
            raise PlatformToolContractError(
                "tool_binding_config_invalid", "whatsapp.send_message requires contract_version=2."
            )
        template_key = config.get("template_key")
        if not isinstance(template_key, str) or not template_key.strip():
            raise PlatformToolContractError("whatsapp_template_required", "whatsapp.send_message requires a template_key.")
        template = self._get_approved_template(tenant_id, template_key)

        recipient = config.get("recipient")
        strategy = recipient.get("strategy") if isinstance(recipient, dict) else None
        if strategy not in _WHATSAPP_RECIPIENT_STRATEGIES:
            raise PlatformToolContractError(
                "tool_binding_config_invalid",
                f"whatsapp.send_message recipient.strategy must be one of {sorted(_WHATSAPP_RECIPIENT_STRATEGIES)}.",
            )

        variables_config = config.get("variables")
        if not isinstance(variables_config, dict):
            raise PlatformToolContractError("whatsapp_variable_mapping_incomplete", "whatsapp.send_message requires a variables mapping.")
        required_keys = WhatsAppTemplateService(self.db).get_approved_parameter_keys(template)
        missing = [key for key in required_keys if key not in variables_config]
        if missing:
            raise PlatformToolContractError(
                "whatsapp_variable_mapping_incomplete", f"Missing variable mapping for: {', '.join(sorted(missing))}."
            )
        for key in required_keys:
            self._validate_whatsapp_variable_spec(key, variables_config[key])

    def _validate_whatsapp_variable_spec(self, key: str, spec: Any) -> None:
        if not isinstance(spec, dict):
            raise PlatformToolContractError("whatsapp_variable_source_invalid", f"variables.{key} must be an object.")
        source = spec.get("source")
        if source not in _WHATSAPP_VARIABLE_SOURCES:
            raise PlatformToolContractError(
                "whatsapp_variable_source_invalid", f"variables.{key}.source must be one of {sorted(_WHATSAPP_VARIABLE_SOURCES)}."
            )
        if source == "llm":
            if spec.get("type") not in _WHATSAPP_LLM_VARIABLE_TYPES:
                raise PlatformToolContractError(
                    "whatsapp_variable_source_invalid", f"variables.{key}.type must be one of {sorted(_WHATSAPP_LLM_VARIABLE_TYPES)}."
                )
        elif source == "context":
            path = spec.get("path")
            if path not in _WHATSAPP_ALLOWED_CONTEXT_PATHS:
                raise PlatformToolContractError(
                    "whatsapp_variable_source_invalid", f"variables.{key}.path is not an allowed context path."
                )
        elif source == "fixed" and "value" not in spec:
            raise PlatformToolContractError("whatsapp_variable_source_invalid", f"variables.{key}.value is required for source=fixed.")

    def _compile_whatsapp_llm_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        variables_config = config.get("variables") if isinstance(config, dict) else None
        properties: dict[str, Any] = {}
        required: list[str] = []
        if isinstance(variables_config, dict):
            for key, spec in variables_config.items():
                if not isinstance(spec, dict) or spec.get("source") != "llm":
                    continue
                properties[key] = {"type": spec.get("type", "string"), "description": spec.get("description", "")}
                required.append(key)
        return {"type": "object", "properties": properties, "required": required}

    def _resolve_whatsapp_variable(
        self, key: str, spec: dict[str, Any], invocation: PlatformToolInvocation, context_dump: dict[str, Any]
    ) -> str:
        source = spec.get("source")
        if source == "llm":
            value = invocation.llm_args.get(key)
            if value is None or value == "":
                raise PlatformToolContractError("tool_argument_invalid", f"Missing LLM argument '{key}'.")
            return str(value)
        if source == "context":
            path = str(spec.get("path") or "")
            try:
                value = resolve_path({"context": context_dump}, f"context.{path}", allow_list_index=False)
            except MappingPathError as exc:
                raise PlatformToolContractError("tool_context_value_missing", f"Context value missing for '{key}' ({path}).") from exc
            if value is None or value == "":
                raise PlatformToolContractError("tool_context_value_missing", f"Context value missing for '{key}' ({path}).")
            return str(value)
        if source == "fixed":
            return str(spec.get("value", ""))
        raise PlatformToolContractError("whatsapp_variable_source_invalid", f"Unknown source for variable '{key}'.")

    def _resolve_whatsapp_recipient(self, strategy: str | None, context_dump: dict[str, Any]) -> str:
        contact_phone = (context_dump.get("contact") or {}).get("phone")
        caller_phone = (context_dump.get("caller") or {}).get("phone")
        if strategy == "contact":
            phone = contact_phone
        elif strategy == "caller":
            phone = caller_phone
        elif strategy == "contact_then_caller":
            phone = contact_phone or caller_phone
        else:
            raise PlatformToolContractError("whatsapp_recipient_context_required", "Unknown or missing recipient strategy.")
        if not phone:
            raise PlatformToolContractError(
                "whatsapp_recipient_context_required", "No trusted recipient phone available in session context."
            )
        return str(phone)

    def _get_approved_template(self, tenant_id: str, template_key: str) -> TenantWhatsAppTemplate:
        template = self.db.scalar(
            select(TenantWhatsAppTemplate).where(
                TenantWhatsAppTemplate.tenant_id == tenant_id,
                TenantWhatsAppTemplate.template_key == template_key,
            )
        )
        if template is None:
            raise PlatformToolContractError("whatsapp_template_not_found", f"WhatsApp template '{template_key}' not found for this tenant.")
        if template.status != "approved":
            raise PlatformToolContractError("whatsapp_template_not_approved", f"WhatsApp template '{template_key}' is not approved.")
        return template

    @staticmethod
    def _path_has_value(context_dump: dict[str, Any], path: str) -> bool:
        try:
            value = resolve_path({"context": context_dump}, f"context.{path}", allow_list_index=False)
        except MappingPathError:
            return False
        return value is not None and value != ""
