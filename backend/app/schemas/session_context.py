"""SessionContextV1: the resolved, tenant-scoped business context of a
VoiceSession -- who's calling, what contact/lead/campaign they represent,
and controlled business variables.

Built once by ContactResolutionService, snapshotted onto
VoiceSession.session_context_json, and compiled unchanged into
RuntimeSessionSpecV1.context by AgentCompilerService. Deliberately
provider-agnostic (nothing Ultravox-specific) and carries no secrets --
same discipline as AgentVoiceConfig/RealtimeModelSpec in this package,
duplicated rather than imported to keep each contract file self-contained
(same convention already used between schemas/agents.py and
schemas/runtime_session.py).

Caller != Contact != Lead: a caller is just this call's telecom identity
(a phone number); a Contact is a known person/organization; a Lead is a
commercial process/opportunity that belongs to exactly one Contact (a
Contact can have several Leads). Keep these separate -- never merge them
to save a field.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_FORBIDDEN_VARIABLE_KEY_PARTS = (
    "api_key", "apikey", "secret", "token", "password", "authorization", "header",
)

_MAX_VARIABLE_KEYS = 20
_MAX_VARIABLE_KEY_LENGTH = 60
_MAX_VARIABLE_DEPTH = 2
_MAX_VARIABLES_SERIALIZED_BYTES = 4000


class CallerContext(_StrictModel):
    """The telecom identity of this specific call. May exist even when no
    Contact could be resolved -- a call from an unknown number is still a
    known caller, just an unresolved one."""

    phone: str | None = Field(default=None, max_length=32)


class ContactContext(_StrictModel):
    """A known person/organization, mapped from CrmContact. Never the full
    ORM row -- only what the LLM or a tool handler legitimately needs."""

    id: str = Field(min_length=1, max_length=36)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=200)


class LeadContext(_StrictModel):
    """One specific commercial process/opportunity belonging to `contact`
    -- never the Contact's full lead history, always the single Lead
    resolved for this session."""

    id: str = Field(min_length=1, max_length=36)
    status: str | None = Field(default=None, max_length=32)
    stage: str | None = Field(default=None, max_length=80)


class CampaignContext(_StrictModel):
    """No real Campaign entity exists in the platform today (see the
    Session Context V1 audit) -- this carries only the free-text
    attribution string already stored on CrmLead.campaign, never an `id`.
    Forward-compatible placeholder for when a real Campaign entity lands;
    adding an `id` later is additive, not a breaking change."""

    name: str | None = Field(default=None, max_length=120)


def _validate_variables(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > _MAX_VARIABLE_KEYS:
        raise ValueError(f"variables cannot have more than {_MAX_VARIABLE_KEYS} keys")

    def check(node: Any, depth: int) -> None:
        if depth > _MAX_VARIABLE_DEPTH:
            raise ValueError("variables cannot be nested more than 2 levels deep")
        if isinstance(node, dict):
            for key, item in node.items():
                if len(str(key)) > _MAX_VARIABLE_KEY_LENGTH:
                    raise ValueError(f"variable key '{key}' exceeds {_MAX_VARIABLE_KEY_LENGTH} characters")
                if any(part in str(key).lower() for part in _FORBIDDEN_VARIABLE_KEY_PARTS):
                    raise ValueError("variables contain a forbidden secret-like key")
                if isinstance(item, (dict, list)):
                    check(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    check(item, depth + 1)

    check(value, 1)
    try:
        serialized = json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("variables must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > _MAX_VARIABLES_SERIALIZED_BYTES:
        raise ValueError(f"variables exceed {_MAX_VARIABLES_SERIALIZED_BYTES} bytes serialized")
    return value


class SessionContextV1(_StrictModel):
    """Every field is optional and the whole object can be entirely empty
    (`{"schema_version": "1"}`) -- a VoiceSession with no resolved context
    (e.g. today's WebRTC test-call flow) keeps working unchanged."""

    schema_version: Literal["1"] = "1"
    source: Literal["webrtc", "inbound", "outbound", "campaign", "manual"] | None = None

    caller: CallerContext | None = None
    contact: ContactContext | None = None
    lead: LeadContext | None = None
    campaign: CampaignContext | None = None

    variables: dict[str, Any] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_variables(value)
