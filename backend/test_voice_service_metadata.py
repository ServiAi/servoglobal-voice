import os
import unittest
from unittest.mock import patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test-ultravox-key")
os.environ.setdefault("DEFAULT_AGENT_ID", "agent-default")
os.environ.setdefault("BOOTSTRAP_TENANT_SLUG", "serviglobal-ia")
os.environ.setdefault("ASTERISK_PUBLIC_HOST", "pbx.example.test")
os.environ.setdefault("UVX_SIP_USERNAME", "sip-user")
os.environ.setdefault("UVX_SIP_PASSWORD", "sip-password")

from app.core.config import settings
from app.services.voice_service import (
    create_call_session,
    create_scheduled_sip_call_via_pbx,
    create_sip_call_via_pbx,
)


class FakeUltravoxResponse:
    text = "{}"

    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class CapturingAsyncClient:
    posts: list[dict] = []
    response_payload: dict = {"joinUrl": "https://join.example.test/call"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers, timeout):
        self.__class__.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeUltravoxResponse(self.__class__.response_payload)


class VoiceServiceMetadataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        CapturingAsyncClient.posts = []
        CapturingAsyncClient.response_payload = {
            "joinUrl": "https://join.example.test/call",
            "callId": "call-test",
        }
        settings.ULTRAVOX_API_KEY = "test-ultravox-key"
        settings.DEFAULT_AGENT_ID = "agent-default"
        settings.BOOTSTRAP_TENANT_SLUG = "serviglobal-ia"
        settings.ASTERISK_PUBLIC_HOST = "pbx.example.test"
        settings.UVX_SIP_USERNAME = "sip-user"
        settings.UVX_SIP_PASSWORD = "sip-password"

    async def test_web_call_session_includes_tenant_slug_metadata(self):
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            join_url = await create_call_session(template_context={"lead": "demo"})

        self.assertEqual(join_url, "https://join.example.test/call")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        self.assertEqual(
            sent_payload["metadata"],
            {"tenant_slug": "serviglobal-ia"},
        )
        self.assertEqual(sent_payload["templateContext"], {"lead": "demo"})

    async def test_immediate_sip_call_includes_tenant_slug_metadata(self):
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            result = await create_sip_call_via_pbx(
                phone="3001112233",
                template_context={"user_name": "Demo User"},
            )

        self.assertEqual(result["callId"], "call-test")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        self.assertEqual(
            sent_payload["metadata"],
            {"tenant_slug": "serviglobal-ia"},
        )
        self.assertEqual(sent_payload["templateContext"], {"user_name": "Demo User"})
        self.assertEqual(
            sent_payload["medium"]["sip"]["outgoing"]["to"],
            "sip:+573001112233@pbx.example.test:5060",
        )

    async def test_scheduled_sip_call_includes_tenant_slug_metadata_per_call_config(self):
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            result = await create_scheduled_sip_call_via_pbx(
                phone="3001112233",
                schedule_time="2026-05-20T15:00:00Z",
                template_context={"user_name": "Demo User"},
            )

        self.assertEqual(result["callId"], "call-test")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        call_config = sent_payload["calls"][0]
        self.assertEqual(
            call_config["metadata"],
            {"tenant_slug": "serviglobal-ia"},
        )
        self.assertEqual(call_config["templateContext"], {"user_name": "Demo User"})
        self.assertEqual(sent_payload["windowStart"], "2026-05-20T15:00:00Z")


if __name__ == "__main__":
    unittest.main()
