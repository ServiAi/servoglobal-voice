from __future__ import annotations

from pydantic import BaseModel, Field


class AsteriskDesiredRoute(BaseModel):
    route_id: str
    route_key: str
    desired_revision: int
    applied_revision: int
    enabled: bool
    sip_username: str
    sip_password: str | None = None
    caller_id: str


class AsteriskDesiredStateResponse(BaseModel):
    snapshot_revision: str
    routes: list[AsteriskDesiredRoute]


class AsteriskApplyResult(BaseModel):
    route_id: str
    revision: int = Field(ge=0)
    success: bool
    error_code: str | None = Field(None, pattern=r"^[a-z0-9_]{1,80}$")


class AsteriskApplyResultsRequest(BaseModel):
    results: list[AsteriskApplyResult] = Field(max_length=500)


class AsteriskApplyResultsResponse(BaseModel):
    accepted: int
    ignored: int
