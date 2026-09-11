"""Contract returned by the internal Control Plane credential endpoint.

Consumed only by the Voice Runtime over the authenticated internal channel
(see app.security.voice_runtime_auth); never returned to a tenant-facing
endpoint or the frontend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProviderCredentialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    api_key: str
    base_url: str | None = None
