from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


# Context fields the visitor fills in BEFORE the call: the only ones that may feed the agent.
# ``internal_only`` and ``collect_during_call`` values never reach the runtime context.
PUBLIC_CONTEXT_COLLECTION_MODES = frozenset({"ask_if_missing", "prefill_and_confirm", "trust_prefill"})

LAUNCH_RUNTIME_LEGACY = "legacy_provider"
LAUNCH_RUNTIME_CANONICAL = "canonical_voice_session"


@dataclass(frozen=True, slots=True)
class VoiceExperienceLimits:
    max_experiences: int
    max_context_fields: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> VoiceExperienceLimits:
        limits = cls(
            max_experiences=int(values["max_experiences"]),
            max_context_fields=int(values["max_context_fields"]),
        )
        if limits.max_experiences < 1 or limits.max_context_fields < 1:
            raise ValueError("Voice experience limits must be positive integers.")
        return limits
