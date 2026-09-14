from __future__ import annotations

import json
import unittest

from livekit.agents import llm

from serviglobal_voice_runtime.contracts import CompiledToolSpec
from serviglobal_voice_runtime.control_plane import ToolInvocationError
from serviglobal_voice_runtime.tool_dispatcher import build_tools


class FakeControlPlane:
    def __init__(self, *, result: dict | None = None, error: ToolInvocationError | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, dict]] = []

    async def invoke_tool(self, session_id: str, tool_key: str, arguments: dict) -> dict:
        self.calls.append((session_id, tool_key, arguments))
        if self.error is not None:
            raise self.error
        return self.result or {}


def _spec(key: str = "calendar.check_availability") -> CompiledToolSpec:
    return CompiledToolSpec(
        key=key, name="Consultar disponibilidad", description="Consulta franjas horarias.",
        input_schema={"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]},
    )


class BuildToolsTests(unittest.IsolatedAsyncioTestCase):
    def test_builds_one_raw_function_tool_per_spec_with_matching_schema(self) -> None:
        control_plane = FakeControlPlane()
        tools = build_tools(control_plane, "session-1", [_spec(), _spec(key="whatsapp.send_message")])

        self.assertEqual(len(tools), 2)
        for tool in tools:
            self.assertIsInstance(tool, llm.RawFunctionTool)
        self.assertEqual(tools[0].info.name, "calendar.check_availability")
        self.assertEqual(tools[0].info.raw_schema["description"], "Consulta franjas horarias.")
        self.assertEqual(tools[0].info.raw_schema["parameters"], _spec().input_schema)
        self.assertEqual(tools[1].info.name, "whatsapp.send_message")

    def test_no_specs_builds_no_tools(self) -> None:
        self.assertEqual(build_tools(FakeControlPlane(), "session-1", []), [])

    async def test_handler_dispatches_to_control_plane_and_returns_json(self) -> None:
        control_plane = FakeControlPlane(result={"date": "2026-09-15", "slots": ["10:00"]})
        [tool] = build_tools(control_plane, "session-1", [_spec()])

        output = await tool(raw_arguments={"date": "mañana"})

        self.assertEqual(json.loads(output), {"date": "2026-09-15", "slots": ["10:00"]})
        self.assertEqual(control_plane.calls, [("session-1", "calendar.check_availability", {"date": "mañana"})])

    async def test_handler_raises_tool_error_on_control_plane_failure(self) -> None:
        control_plane = FakeControlPlane(error=ToolInvocationError("tool_integration_not_configured", status_code=422))
        [tool] = build_tools(control_plane, "session-1", [_spec()])

        with self.assertRaises(llm.ToolError) as ctx:
            await tool(raw_arguments={"date": "mañana"})
        self.assertIn("tool_integration_not_configured", str(ctx.exception))

    async def test_each_built_tool_is_scoped_to_its_own_key(self) -> None:
        # Two tools built from the same spec list must never cross-dispatch
        # -- calling one must never invoke the other's key.
        control_plane = FakeControlPlane(result={"status": "sent"})
        availability_tool, whatsapp_tool = build_tools(
            control_plane, "session-1", [_spec(), _spec(key="whatsapp.send_message")]
        )

        await whatsapp_tool(raw_arguments={"to_phone": "+573000000001", "template_key": "x"})

        self.assertEqual(control_plane.calls, [("session-1", "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "x"})])


if __name__ == "__main__":
    unittest.main()
