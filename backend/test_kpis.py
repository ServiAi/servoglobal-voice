import os
import sys

os.environ['DATABASE_URL'] = os.environ['STAGING_DATABASE_URL']

from fastapi.testclient import TestClient
from app.main import app
from app.api.auth.deps import get_current_identity
from app.services.auth0_service import AuthenticatedIdentity

async def _identity_override():
    return AuthenticatedIdentity(
        external_auth_id="auth0|69f7dba26aea0d1fa52cdd37",
        email="ventas-ia@serviglobal.co",
        name="Test Staging User",
        claims={"sub": "auth0|69f7dba26aea0d1fa52cdd37", "email": "ventas-ia@serviglobal.co"},
    )

app.dependency_overrides[get_current_identity] = _identity_override
client = TestClient(app)

print(client.get("/api/v1/dashboard/kpis").json())
