from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from livekit.agents import RunContext, llm

from .contracts import CompiledToolSpec
from .control_plane import ControlPlaneClient, ToolInvocationError


_SAFE_INVOCATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def invocation_id_from_call_id(call_id: str | None) -> str:
    """Stable, backend-acceptable identity of one logical tool call, derived from
    LiveKit's ``FunctionCall.call_id`` (never from the LLM's arguments).

    Same call_id -> same id (identity when it already fits the backend's
    allowlist; otherwise a deterministic digest). A missing call_id fails
    closed: a random id would silently defeat idempotency."""
    if not call_id or not call_id.strip():
        raise llm.ToolError("tool_call_identity_unavailable")
    if _SAFE_INVOCATION_ID.match(call_id):
        return call_id
    return "lk-" + hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:40]


def build_tools(
    control_plane: ControlPlaneClient, session_id: str, specs: list[CompiledToolSpec]
) -> list[llm.FunctionTool]:
    """Builds one RawFunctionTool per CompiledToolSpec, registered with the
    Agent so the LLM can call it by name. Never resolves a handler locally:
    this process holds no DB session and no tenant credentials, so every
    call is dispatched back to the backend's internal tool-invoke endpoint,
    which re-validates the binding and runs the real (allowlisted) handler.
    This function only wires the LLM-facing shape
    (name/description/input_schema) to that single generic HTTP dispatch.
    """

    def make_handler(tool_key: str):
        async def handler(ctx: RunContext, raw_arguments: dict[str, Any]) -> str:
            # ctx is injected by LiveKit (by type); it is not part of the LLM schema.
            invocation_id = invocation_id_from_call_id(ctx.function_call.call_id)
            try:
                result = await control_plane.invoke_tool(
                    session_id, tool_key, raw_arguments, invocation_id=invocation_id
                )
            except ToolInvocationError as exc:
                # Surfaced to the LLM via the framework's normal tool-error
                # path (function_call_output.is_error) -- see
                # livekit.agents.llm.tool_context.ToolError's docstring.
                raise llm.ToolError(str(exc)) from exc
            return json.dumps(result)

        return handler

    return [
        llm.function_tool(
            make_handler(spec.key),
            raw_schema={"name": spec.key, "description": spec.description, "parameters": spec.input_schema},
        )
        for spec in specs
    ]
