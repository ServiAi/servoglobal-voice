from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from livekit.agents import llm

from serviglobal_voice_runtime.contracts import CompiledToolSpec
from serviglobal_voice_runtime.control_plane import ToolInvocationError
from serviglobal_voice_runtime.tool_dispatcher import build_tools, invocation_id_from_call_id


class FakeControlPlane:
    def __init__(self, *, result: dict | None = None, error: ToolInvocationError | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, dict, str]] = []

    async def invoke_tool(self, session_id: str, tool_key: str, arguments: dict, *, invocation_id: str) -> dict:
        self.calls.append((session_id, tool_key, arguments, invocation_id))
        if self.error is not None:
            raise self.error
        return self.result or {}


def _ctx(call_id: str | None = "call-1"):
    # LiveKit injects a RunContext whose function_call carries the call_id.
    return SimpleNamespace(function_call=SimpleNamespace(call_id=call_id))


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

        output = await tool(ctx=_ctx("call-123"), raw_arguments={"date": "mañana"})

        self.assertEqual(json.loads(output), {"date": "2026-09-15", "slots": ["10:00"]})
        self.assertEqual(control_plane.calls, [("session-1", "calendar.check_availability", {"date": "mañana"}, "call-123")])

    async def test_handler_raises_tool_error_on_control_plane_failure(self) -> None:
        control_plane = FakeControlPlane(error=ToolInvocationError("tool_integration_not_configured", status_code=422))
        [tool] = build_tools(control_plane, "session-1", [_spec()])

        with self.assertRaises(llm.ToolError) as ctx:
            await tool(ctx=_ctx(), raw_arguments={"date": "mañana"})
        self.assertIn("tool_integration_not_configured", str(ctx.exception))

    async def test_each_built_tool_is_scoped_to_its_own_key(self) -> None:
        # Two tools built from the same spec list must never cross-dispatch
        # -- calling one must never invoke the other's key.
        control_plane = FakeControlPlane(result={"status": "sent"})
        availability_tool, whatsapp_tool = build_tools(
            control_plane, "session-1", [_spec(), _spec(key="whatsapp.send_message")]
        )

        await whatsapp_tool(ctx=_ctx("call-9"), raw_arguments={"to_phone": "+573000000001", "template_key": "x"})

        self.assertEqual(control_plane.calls, [("session-1", "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "x"}, "call-9")])


    async def test_same_call_id_same_invocation_id_and_different_ids_differ(self) -> None:
        control_plane = FakeControlPlane(result={})
        [tool] = build_tools(control_plane, "session-1", [_spec()])
        for call_id in ("call-1", "call-1", "call-2"):
            await tool(ctx=_ctx(call_id), raw_arguments={"date": "x"})
        self.assertEqual([c[3] for c in control_plane.calls], ["call-1", "call-1", "call-2"])

    async def test_llm_arguments_cannot_set_the_invocation_id(self) -> None:
        control_plane = FakeControlPlane(result={})
        [tool] = build_tools(control_plane, "session-1", [_spec()])
        await tool(ctx=_ctx("call-real"), raw_arguments={"date": "x", "invocation_id": "evil"})
        self.assertEqual(control_plane.calls[0][3], "call-real")  # trusted source only

    def test_tool_schema_does_not_expose_call_or_invocation_id(self) -> None:
        [tool] = build_tools(FakeControlPlane(), "session-1", [_spec()])
        params = tool.info.raw_schema["parameters"]
        self.assertNotIn("invocation_id", params["properties"])
        self.assertNotIn("call_id", params["properties"])

    def test_unsafe_call_ids_are_normalised_deterministically_and_missing_fails_closed(self) -> None:
        odd = "call/with spaces+n"
        self.assertEqual(invocation_id_from_call_id("call_AbC-1.x"), "call_AbC-1.x")
        self.assertEqual(invocation_id_from_call_id(odd), invocation_id_from_call_id(odd))
        self.assertTrue(invocation_id_from_call_id(odd).startswith("lk-"))
        self.assertNotEqual(invocation_id_from_call_id(odd), invocation_id_from_call_id(odd + "2"))
        self.assertLessEqual(len(invocation_id_from_call_id("x" * 300)), 64)
        for missing in (None, "", "  "):
            with self.assertRaises(llm.ToolError):
                invocation_id_from_call_id(missing)

    async def test_framework_injects_run_context_by_type(self) -> None:
        # The handler must be bindable by LiveKit: ctx is resolved from its annotation.
        from livekit.agents.llm.utils import prepare_function_arguments
        from livekit.agents.voice.events import RunContext

        [tool] = build_tools(FakeControlPlane(), "session-1", [_spec()])
        fake_ctx = object.__new__(RunContext)
        args, kwargs = prepare_function_arguments(fnc=tool, json_arguments={"date": "x"}, call_ctx=fake_ctx)
        bound = {**dict(zip(["ctx", "raw_arguments"], args)), **kwargs}
        self.assertIs(bound["ctx"], fake_ctx)
        self.assertEqual(bound["raw_arguments"], {"date": "x"})


if __name__ == "__main__":
    unittest.main()
