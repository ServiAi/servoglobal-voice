from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    user_id: str
    email: str
    name: str | None
    tenant_id: str
    tenant_name: str
    role: str
    is_internal: bool

    model_config = ConfigDict(from_attributes=True)
