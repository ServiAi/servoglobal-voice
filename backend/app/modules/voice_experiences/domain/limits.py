from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


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
