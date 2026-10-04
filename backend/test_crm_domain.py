"""Pure CRM domain rules: no database, no framework, no network."""

import dataclasses
import unittest
from datetime import UTC, datetime

from app.modules.crm.domain.calls import BookingDetection, CallClassification, CallRef, ContextLookup
from app.modules.crm.domain.contacts import normalize_phone
from app.modules.crm.domain.pipeline import (
    AUTOMATIC_TRANSITIONS,
    DEFAULT_STAGE_KEYS,
    DEFAULT_STAGES,
    TERMINAL_STAGES,
    VALID_LEAD_STATUSES,
)
from app.modules.crm.domain.tasks import VALID_TASK_PRIORITIES, VALID_TASK_STATUSES
from app.modules.crm.domain.views import (
    ActivityView,
    CallContextView,
    ContactProfile,
    CrmFunnelSnapshot,
    LeadProfile,
    VoiceCallView,
)


class PipelineRulesTests(unittest.TestCase):
    def test_default_stages_are_a_single_ordered_pipeline_with_one_default(self) -> None:
        positions = [stage["position"] for stage in DEFAULT_STAGES]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), len(positions))
        self.assertEqual([s["key"] for s in DEFAULT_STAGES if s["is_default"]], ["new"])
        self.assertEqual(DEFAULT_STAGE_KEYS, {stage["key"] for stage in DEFAULT_STAGES})

    def test_terminal_stages_match_the_stage_flags(self) -> None:
        flagged = {stage["key"] for stage in DEFAULT_STAGES if stage["is_terminal"]}
        self.assertEqual(flagged, {"not_interested", "won", "lost"})
        self.assertEqual(TERMINAL_STAGES, flagged)

    def test_automatic_transitions_only_use_known_stages_and_never_leave_terminal_ones(self) -> None:
        self.assertEqual(set(AUTOMATIC_TRANSITIONS), DEFAULT_STAGE_KEYS)
        for source, targets in AUTOMATIC_TRANSITIONS.items():
            self.assertLessEqual(targets, DEFAULT_STAGE_KEYS, source)
            self.assertNotIn(source, targets)
        for terminal in TERMINAL_STAGES:
            self.assertEqual(AUTOMATIC_TRANSITIONS[terminal], set())
        self.assertEqual(AUTOMATIC_TRANSITIONS["scheduled"], set())

    def test_valid_statuses_and_task_vocabularies(self) -> None:
        self.assertEqual(VALID_LEAD_STATUSES, {"open", "won", "lost", "unqualified", "paused"})
        self.assertEqual(VALID_TASK_STATUSES, {"pending", "done", "cancelled", "overdue"})
        self.assertEqual(VALID_TASK_PRIORITIES, {"low", "medium", "high"})


class ContactRulesTests(unittest.TestCase):
    def test_normalize_phone(self) -> None:
        self.assertEqual(normalize_phone("+57 (300) 111-22-33"), "+573001112233")
        self.assertEqual(normalize_phone("3001112233"), "+573001112233")  # Colombian 10-digit fallback
        self.assertEqual(normalize_phone("+14155550100"), "+14155550100")
        self.assertIsNone(normalize_phone(None))
        self.assertIsNone(normalize_phone(" - "))


class ViewsAreImmutableTests(unittest.TestCase):
    def test_every_view_is_a_frozen_dataclass(self) -> None:
        for cls in (
            CallRef, BookingDetection, CallClassification, ContextLookup, ContactProfile, LeadProfile,
            ActivityView, CallContextView, VoiceCallView, CrmFunnelSnapshot,
        ):
            self.assertTrue(dataclasses.is_dataclass(cls), cls)
            self.assertTrue(cls.__dataclass_params__.frozen, f"{cls.__name__} must be frozen")

    def test_a_view_cannot_be_mutated(self) -> None:
        call = CallRef(id="c1", tenant_id="t1", joined_at=datetime(2026, 1, 1, tzinfo=UTC))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            call.id = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
