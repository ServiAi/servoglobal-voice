from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.billing import TenantPlanRequest, TenantUsageResponse


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=120)
    timezone: str = Field(default="America/Bogota", max_length=80)
    status: str = Field(default="active", max_length=32)
    plan: TenantPlanRequest = Field(
        default_factory=lambda: TenantPlanRequest(plan_key="web_conversion")
    )
    admin: AdminCreateRequest = Field(...)
    agents: list[AgentCreateRequest] = Field(default_factory=list)


class AdminCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1)
    role: str = Field(default="tenant_admin", min_length=1, max_length=64)


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    external_provider: str = Field(..., min_length=1, max_length=80)
    external_agent_id: str = Field(..., min_length=1, max_length=255)
    channel_type: str | None = Field(default=None, max_length=80)
    status: str = Field(default="active", max_length=32)


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=32)


class MembershipCreateRequest(BaseModel):
    email: str = Field(..., min_length=1)
    role: str = Field(default="tenant_analyst", min_length=1, max_length=64)


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    timezone: str
    status: str
    admin: dict[str, Any] | None = None
    memberships: list[dict[str, Any]] = Field(default_factory=list)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    usage: TenantUsageResponse | None = None
    is_ready_for_calls: bool = False


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    external_provider: str | None = None
    external_agent_id: str | None = None
    channel_type: str | None = None
    status: str


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    user_id: str
    role: str
    status: str
    user_email: str | None = None
    user_name: str | None = None
