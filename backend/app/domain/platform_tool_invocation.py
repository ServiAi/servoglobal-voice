from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.session_context import SessionContextV1


@dataclass
class PlatformToolInvocation:
    """The three sources a Platform Tool handler is allowed to read, kept
    separate on purpose -- see PlatformToolContractService. Never merge
    these into one dict (`{**llm_args, **context, **config}`): that erases
    which source a value came from, which is exactly the trust boundary
    this contract exists to preserve.

    llm_args: what the model decided this call (validated against the
        tool's effective LLM schema).
    context: the session's own resolved SessionContextV1 (caller/contact/
        lead/campaign) -- trusted, never LLM-supplied.
    config: the admin's AgentToolBinding.config for this tool on the
        published version -- fixed policy, never model- or caller-supplied.
    """

    llm_args: dict[str, Any]
    context: SessionContextV1
    config: dict[str, Any]
