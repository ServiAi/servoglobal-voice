from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_preflight_accepts_serviglobal_subdomains():
    response = client.options(
        "/api/v1/dashboard/recent-calls",
        headers={
            "Origin": "https://app.serviglobal-ia.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.serviglobal-ia.com"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_preflight_rejects_unknown_origins():
    response = client.options(
        "/api/v1/dashboard/recent-calls",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 400
