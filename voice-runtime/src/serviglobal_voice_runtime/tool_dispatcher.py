from __future__ import annotations

import json
from typing import Any

from livekit.agents import llm

from .contracts import CompiledToolSpec
from .control_plane import ControlPlaneClient, ToolInvocationError


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
        async def handler(raw_arguments: dict[str, Any]) -> str:
            try:
                result = await control_plane.invoke_tool(session_id, tool_key, raw_arguments)
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
