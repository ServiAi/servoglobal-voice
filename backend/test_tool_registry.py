from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.domain import tool_registry


class ToolRegistryTests(unittest.TestCase):
    def test_catalog_has_the_four_v1_available_tools(self) -> None:
        # calendar.create_booking and crm.create_lead were reactivated by
        # Session Context V1 (lead_id/contact_id/caller phone now come
        # from SessionContextV1 server-side, never the LLM).
        available = {t.key for t in tool_registry.list_tools(status="available")}
        self.assertEqual(
            available,
            {"calendar.check_availability", "whatsapp.send_message", "calendar.create_booking", "crm.create_lead"},
        )

    def test_planned_tools_are_documented_but_not_available(self) -> None:
        # handoff.chatwoot stays planned: VoiceHandoffService requires a
        # full legacy TenantVoiceAgentConfig object, unrelated to Session
        # Context V1 -- see app/domain/tool_registry.py's own comment.
        planned = {t.key for t in tool_registry.list_tools(status="planned")}
        self.assertEqual(planned, {"handoff.chatwoot"})

    def test_get_tool_returns_none_for_unknown_key(self) -> None:
        self.assertIsNone(tool_registry.get_tool("does.not_exist"))

    def test_available_tools_declare_required_integration_and_input_schema(self) -> None:
        for tool in tool_registry.list_tools(status="available"):
            self.assertIsNotNone(tool.required_integration)
            self.assertEqual(tool.input_schema.get("type"), "object")
            self.assertIn("properties", tool.input_schema)

    def test_validate_tool_bindings_accepts_available_tools(self) -> None:
        bindings = [
            SimpleNamespace(key="calendar.check_availability"),
            SimpleNamespace(key="whatsapp.send_message"),
        ]
        tool_registry.validate_tool_bindings(bindings)  # does not raise

    def test_validate_tool_bindings_rejects_unknown_key(self) -> None:
        with self.assertRaises(tool_registry.ToolRegistryValidationError) as ctx:
            tool_registry.validate_tool_bindings([SimpleNamespace(key="does.not_exist")])
        self.assertIn("tool_not_found", str(ctx.exception))

    def test_validate_tool_bindings_rejects_planned_tool(self) -> None:
        with self.assertRaises(tool_registry.ToolRegistryValidationError) as ctx:
            tool_registry.validate_tool_bindings([SimpleNamespace(key="handoff.chatwoot")])
        self.assertIn("tool_not_available", str(ctx.exception))

    def test_validate_tool_bindings_rejects_duplicate_key(self) -> None:
        bindings = [
            SimpleNamespace(key="calendar.check_availability"),
            SimpleNamespace(key="calendar.check_availability"),
        ]
        with self.assertRaises(tool_registry.ToolRegistryValidationError):
            tool_registry.validate_tool_bindings(bindings)

    def test_validate_tool_bindings_accepts_empty_list(self) -> None:
        tool_registry.validate_tool_bindings([])  # does not raise


if __name__ == "__main__":
    unittest.main()
