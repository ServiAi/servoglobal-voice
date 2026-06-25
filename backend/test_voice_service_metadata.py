import os
import unittest
from unittest.mock import patch
import httpx

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
        context = {"lead": "demo", "context_id": "ctx-1", "form_submission_id": "form-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            join_url = await create_call_session(template_context=context)

        self.assertEqual(join_url, "https://join.example.test/call")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        self.assertEqual(
            sent_payload["metadata"],
            {
                "tenant_slug": "serviglobal-ia",
                "context_id": "ctx-1",
                "crm_context_id": "ctx-1",
                "form_submission_id": "form-1",
            },
        )
        self.assertEqual(sent_payload["templateContext"], context)

    async def test_immediate_sip_call_includes_tenant_slug_metadata(self):
        context = {"user_name": "Demo User", "context_id": "ctx-1", "form_submission_id": "form-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            result = await create_sip_call_via_pbx(
                phone="3001112233",
                template_context=context,
            )

        self.assertEqual(result["callId"], "call-test")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        self.assertEqual(
            sent_payload["metadata"],
            {
                "tenant_slug": "serviglobal-ia",
                "context_id": "ctx-1",
                "crm_context_id": "ctx-1",
                "form_submission_id": "form-1",
            },
        )
        self.assertEqual(sent_payload["templateContext"], context)
        self.assertEqual(
            sent_payload["medium"]["sip"]["outgoing"]["to"],
            "sip:+573001112233@pbx.example.test:5060",
        )

    async def test_scheduled_sip_call_includes_tenant_slug_metadata_per_call_config(self):
        context = {"user_name": "Demo User", "context_id": "ctx-1", "form_submission_id": "form-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            result = await create_scheduled_sip_call_via_pbx(
                phone="3001112233",
                schedule_time="2026-05-20T15:00:00Z",
                template_context=context,
            )

        self.assertEqual(result["callId"], "call-test")
        sent_payload = CapturingAsyncClient.posts[0]["json"]
        call_config = sent_payload["calls"][0]
        self.assertEqual(
            call_config["metadata"],
            {
                "tenant_slug": "serviglobal-ia",
                "context_id": "ctx-1",
                "crm_context_id": "ctx-1",
                "form_submission_id": "form-1",
            },
        )
        self.assertEqual(call_config["templateContext"], context)
        self.assertEqual(sent_payload["windowStart"], "2026-05-20T15:00:00Z")

    async def test_sip_call_does_not_log_payload_or_password(self):
        context = {"user_name": "Sensitive User", "user_email": "sensitive@test.com", "context_id": "ctx-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            with self.assertLogs("app.services.voice_service", level="INFO") as log_capture:
                await create_sip_call_via_pbx(
                    phone="3001112233",
                    template_context=context,
                )

        log_output = "\n".join(log_capture.output)
        self.assertNotIn("sip-password", log_output)
        self.assertNotIn("sensitive@test.com", log_output)
        self.assertNotIn("3001112233", log_output)
        self.assertNotIn("+573001112233", log_output)
        self.assertIn("phone_tail=***2233", log_output)
        self.assertIn("has_context_id=True", log_output)

    async def test_scheduled_sip_call_does_not_log_payload_or_password(self):
        context = {"user_name": "Sensitive User", "user_email": "sensitive@test.com", "context_id": "ctx-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            with self.assertLogs("app.services.voice_service", level="INFO") as log_capture:
                await create_scheduled_sip_call_via_pbx(
                    phone="3001112233",
                    schedule_time="2026-05-20T15:00:00Z",
                    template_context=context,
                )

        log_output = "\n".join(log_capture.output)
        self.assertNotIn("sip-password", log_output)
        self.assertNotIn("sensitive@test.com", log_output)
        self.assertNotIn("3001112233", log_output)
        self.assertNotIn("+573001112233", log_output)
        self.assertIn("phone_tail=***2233", log_output)
        self.assertIn("has_context_id=True", log_output)

    async def test_sip_call_log_masks_phone(self):
        context = {"context_id": "ctx-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", CapturingAsyncClient):
            with self.assertLogs("app.services.voice_service", level="INFO") as log_capture:
                await create_sip_call_via_pbx(
                    phone="3001112233",
                    template_context=context,
                )
        log_output = "\n".join(log_capture.output)
        self.assertIn("phone_tail=***2233", log_output)

    async def test_ultravox_error_log_does_not_include_payload(self):
        class ErrorRaisingAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            async def post(self, url, json, headers, timeout):
                response = httpx.Response(
                    status_code=400,
                    content=b"Invalid voice parameters",
                    request=httpx.Request("POST", url)
                )
                raise httpx.HTTPStatusError("Bad Request", request=response.request, response=response)

        context = {"user_name": "Sensitive User", "user_email": "sensitive@test.com", "context_id": "ctx-1"}
        with patch("app.services.voice_service.httpx.AsyncClient", ErrorRaisingAsyncClient):
            with self.assertLogs("app.services.voice_service", level="ERROR") as log_capture:
                try:
                    await create_sip_call_via_pbx(
                        phone="3001112233",
                        template_context=context,
                    )
                except httpx.HTTPStatusError:
                    pass

        log_output = "\n".join(log_capture.output)
        self.assertNotIn("sip-password", log_output)
        self.assertNotIn("sensitive@test.com", log_output)
        self.assertNotIn("3001112233", log_output)
        self.assertIn("status=400", log_output)
        self.assertIn("Invalid voice parameters", log_output)


if __name__ == "__main__":
    unittest.main()
