from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.agents import AgentToolBinding


class AgentToolBindingSchemaTests(unittest.TestCase):
    """AgentToolBinding validates shape only: key/enabled/config types and
    no secret-like config keys. Whether `key` is a known, executable tool
    is app.domain.tool_registry's job -- see test_tool_registry.py."""

    def test_minimal_binding_defaults_enabled_true_and_empty_config(self) -> None:
        binding = AgentToolBinding(key="calendar.check_availability")
        self.assertTrue(binding.enabled)
        self.assertEqual(binding.config, {})

    def test_disabled_binding_with_config(self) -> None:
        binding = AgentToolBinding(key="whatsapp.send_message", enabled=False, config={"template_key": "booking_confirmation"})
        self.assertFalse(binding.enabled)
        self.assertEqual(binding.config["template_key"], "booking_confirmation")

    def test_empty_key_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AgentToolBinding(key="")

    def test_config_must_be_a_mapping(self) -> None:
        with self.assertRaises(ValidationError):
            AgentToolBinding(key="calendar.check_availability", config=["not", "a", "dict"])

    def test_secret_like_config_key_is_rejected(self) -> None:
        for key in ("api_key", "apikey", "secret", "token", "password", "authorization", "header"):
            with self.assertRaises(ValidationError, msg=key):
                AgentToolBinding(key="whatsapp.send_message", config={key: "leak"})

    def test_config_default_does_not_share_state_across_instances(self) -> None:
        first = AgentToolBinding(key="calendar.check_availability")
        second = AgentToolBinding(key="whatsapp.send_message")
        first.config["leaked"] = True
        self.assertEqual(second.config, {})

    def test_schema_does_not_validate_whether_key_is_a_known_tool(self) -> None:
        # Proves the shape-only boundary: an arbitrary key is a valid shape
        # here -- rejecting unknown/unavailable keys is
        # app.domain.tool_registry.validate_tool_bindings' job.
        AgentToolBinding(key="totally_unknown_tool_key")


if __name__ == "__main__":
    unittest.main()
