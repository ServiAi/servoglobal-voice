"""HTTP contract of the Asterisk endpoints (defined with the provisioning use case)."""

from app.modules.telephony.application.provisioning_schemas import (  # noqa: F401
    AsteriskApplyResult,
    AsteriskApplyResultsRequest,
    AsteriskApplyResultsResponse,
    AsteriskDesiredRoute,
    AsteriskDesiredStateResponse,
)

__all__ = [
    "AsteriskApplyResult",
    "AsteriskApplyResultsRequest",
    "AsteriskApplyResultsResponse",
    "AsteriskDesiredRoute",
    "AsteriskDesiredStateResponse",
]
