from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.session_context import (
    CallerContext,
    CampaignContext,
    ContactContext,
    LeadContext,
    SessionContextV1,
)


class SessionContextV1SchemaTests(unittest.TestCase):
    """SessionContextV1 is the typed, versioned business context a
    VoiceSession carries -- validates shape/secrets/size only. See
    test_contact_resolution_service.py for who actually populates it."""

    def test_empty_context_is_valid(self) -> None:
        ctx = SessionContextV1()
        self.assertEqual(ctx.schema_version, "1")
        self.assertIsNone(ctx.caller)
        self.assertIsNone(ctx.contact)
        self.assertIsNone(ctx.lead)
        self.assertIsNone(ctx.campaign)
        self.assertEqual(ctx.variables, {})

    def test_bare_dict_parses_to_empty_context(self) -> None:
        # {} must keep validating -- today's default for every VoiceSession
        # without a resolved context.
        ctx = SessionContextV1.model_validate({})
        self.assertEqual(ctx, SessionContextV1())

    def test_full_valid_context(self) -> None:
        ctx = SessionContextV1(
            source="outbound",
            caller=CallerContext(phone="+573001234567"),
            contact=ContactContext(id="contact_1", name="Carlos Pérez", phone="+573001234567", email="carlos@example.com"),
            lead=LeadContext(id="lead_1", status="open", stage="qualified"),
            campaign=CampaignContext(name="Cobranza septiembre"),
            variables={"debt_amount": 850000},
        )
        self.assertEqual(ctx.contact.name, "Carlos Pérez")
        self.assertEqual(ctx.lead.status, "open")
        self.assertEqual(ctx.campaign.name, "Cobranza septiembre")

    def test_unknown_top_level_key_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1.model_validate({"lead_id": "lead-9"})

    def test_campaign_context_has_no_id_field(self) -> None:
        with self.assertRaises(ValidationError):
            CampaignContext.model_validate({"id": "campaign-1", "name": "x"})

    def test_secret_like_variable_key_is_rejected(self) -> None:
        for key in ("api_key", "apikey", "secret", "token", "password", "authorization", "header"):
            with self.assertRaises(ValidationError, msg=key):
                SessionContextV1(variables={key: "leak"})

    def test_nested_secret_like_variable_key_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={"nested": {"api_key": "leak"}})

    def test_variables_reject_more_than_20_keys(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={f"key_{i}": i for i in range(21)})

    def test_variables_accept_exactly_20_keys(self) -> None:
        SessionContextV1(variables={f"key_{i}": i for i in range(20)})

    def test_variables_reject_key_longer_than_60_chars(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={"x" * 61: "value"})

    def test_variables_reject_depth_greater_than_2(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={"level1": {"level2": {"level3": "too deep"}}})

    def test_variables_accept_depth_of_2(self) -> None:
        SessionContextV1(variables={"level1": {"level2": "ok"}})

    def test_variables_reject_oversized_payload(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={"blob": "x" * 5000})

    def test_variables_must_be_json_serializable(self) -> None:
        with self.assertRaises(ValidationError):
            SessionContextV1(variables={"bad": {1, 2, 3}})

    def test_context_round_trips_through_json(self) -> None:
        ctx = SessionContextV1(
            caller=CallerContext(phone="+573001234567"),
            lead=LeadContext(id="lead_1", status="open"),
            variables={"debt_amount": 850000},
        )
        dumped = ctx.model_dump_json()
        restored = SessionContextV1.model_validate_json(dumped)
        self.assertEqual(ctx, restored)


if __name__ == "__main__":
    unittest.main()
