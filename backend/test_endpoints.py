import os
import sys
import json

os.environ['DATABASE_URL'] = 'postgresql+psycopg://serviai_user:Pancracio810129%2A%2B@127.0.0.1:15432/serviai_staging'

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

def pretty_print(name, res):
    print(f"--- {name} ---")
    if res.status_code == 200:
        print(json.dumps(res.json(), indent=2)[:500] + '...')
    else:
        print(f"ERROR {res.status_code}: {res.text}")
    print()

pretty_print("1. KPIs", client.get("/api/v1/dashboard/kpis"))
pretty_print("2. Trends", client.get("/api/v1/dashboard/trends"))
pretty_print("3. Status", client.get("/api/v1/dashboard/status-distribution"))
pretty_print("4. Agent", client.get("/api/v1/dashboard/agent-distribution"))
pretty_print("5. Heatmap", client.get("/api/v1/dashboard/heatmap"))
pretty_print("6. Recent", client.get("/api/v1/dashboard/recent-calls?page_size=3"))
pretty_print("7. Filters (answered)", client.get("/api/v1/dashboard/recent-calls?status=answered&page_size=2"))
