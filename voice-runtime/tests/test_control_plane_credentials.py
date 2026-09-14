from __future__ import annotations

import unittest

import httpx

from serviglobal_voice_runtime.config import Settings
from serviglobal_voice_runtime.control_plane import ControlPlaneClient, ToolInvocationError
from serviglobal_voice_runtime.credentials import (
    ControlPlaneCredentialResolver,
    ProviderCredential,
    ProviderCredentialNotConfiguredError,
    ProviderCredentialSessionNotFoundError,
    ProviderCredentialUnavailableError,
    ProviderCredentialUnsupportedError,
)


def settings() -> Settings:
    return Settings(
        CONTROL_PLANE_BASE_URL="http://control-plane",
        VOICE_RUNTIME_SERVICE_SECRET="x" * 32,
        LIVEKIT_URL="wss://example.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        CONTROL_PLANE_MAX_ATTEMPTS=1,
    )


def client_with(handler) -> ControlPlaneClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url="http://control-plane", transport=transport)
    return ControlPlaneClient(settings(), client=http_client)


class ControlPlaneCredentialClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_a_tenant_specific_credential(self) -> None:
        seen_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            self.assertTrue(request.headers["Authorization"].startswith("Bearer "))
            return httpx.Response(200, json={"provider": "ultravox", "api_key": "tenant-a-key", "base_url": None})

        client = client_with(handler)
        credential = await client.get_provider_credential(session_id="session-a", provider="ultravox")

        self.assertEqual(credential, ProviderCredential(provider="ultravox", api_key="tenant-a-key", base_url=None))
        self.assertEqual(seen_paths, ["/api/v1/internal/voice-runtime/sessions/session-a/credentials/ultravox"])
        await client.aclose()

    async def test_missing_session_or_provider_mismatch_raises_not_found(self) -> None:
        client = client_with(lambda request: httpx.Response(404, json={"detail": "Voice session not found."}))
        with self.assertRaises(ProviderCredentialSessionNotFoundError):
            await client.get_provider_credential(session_id="missing", provider="ultravox")
        await client.aclose()

    async def test_inactive_integration_or_missing_key_raises_not_configured(self) -> None:
        client = client_with(lambda request: httpx.Response(409, json={"detail": "provider_credentials_unavailable"}))
        with self.assertRaises(ProviderCredentialNotConfiguredError):
            await client.get_provider_credential(session_id="session-a", provider="ultravox")
        await client.aclose()

    async def test_unsupported_provider_raises_unsupported_error(self) -> None:
        client = client_with(lambda request: httpx.Response(422, json={"detail": "Unsupported voice provider."}))
        with self.assertRaises(ProviderCredentialUnsupportedError):
            await client.get_provider_credential(session_id="session-a", provider="not-a-real-provider")
        await client.aclose()

    async def test_unexpected_failure_raises_unavailable_error_without_leaking_details(self) -> None:
        client = client_with(lambda request: httpx.Response(500, json={"detail": "boom"}))
        with self.assertRaises(ProviderCredentialUnavailableError) as ctx:
            await client.get_provider_credential(session_id="session-a", provider="ultravox")
        self.assertNotIn("boom", str(ctx.exception))
        await client.aclose()


class ControlPlaneToolInvocationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_invokes_a_tool_and_returns_the_result(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = request.read()
            self.assertTrue(request.headers["Authorization"].startswith("Bearer "))
            return httpx.Response(200, json={"result": {"date": "2026-09-15", "slots": []}})

        client = client_with(handler)
        result = await client.invoke_tool("session-a", "calendar.check_availability", {"date": "mañana"})

        self.assertEqual(result, {"date": "2026-09-15", "slots": []})
        self.assertEqual(seen["path"], "/api/v1/internal/voice-runtime/sessions/session-a/tools/calendar.check_availability/invoke")
        self.assertIn(b"ma\xc3\xb1ana", seen["body"])
        await client.aclose()

    async def test_error_response_detail_becomes_the_exception_message(self) -> None:
        client = client_with(lambda request: httpx.Response(422, json={"detail": "tool_argument_invalid:Missing required argument 'date'."}))
        with self.assertRaises(ToolInvocationError) as ctx:
            await client.invoke_tool("session-a", "calendar.check_availability", {})
        self.assertIn("tool_argument_invalid", str(ctx.exception))
        self.assertEqual(ctx.exception.status_code, 422)
        await client.aclose()

    async def test_never_retries_a_5xx_tool_invocation(self) -> None:
        # A tool call can be side-effecting (e.g. sends a WhatsApp message);
        # retrying a transient 5xx here could duplicate that effect. Proven
        # by counting requests, not just asserting the final outcome.
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(502, json={"detail": "tool_execution_failed:boom"})

        client = client_with(handler)
        with self.assertRaises(ToolInvocationError):
            await client.invoke_tool("session-a", "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "x"})
        self.assertEqual(calls["count"], 1)
        await client.aclose()


class ControlPlaneCredentialResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_delegates_to_the_transport_scoped_by_session(self) -> None:
        class FakeTransport:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            async def get_provider_credential(self, *, session_id: str, provider: str) -> ProviderCredential:
                self.calls.append((session_id, provider))
                return ProviderCredential(provider=provider, api_key=f"key-for-{session_id}")

        transport = FakeTransport()
        resolver = ControlPlaneCredentialResolver(transport)

        credential = await resolver.resolve(session_id="session-a", provider="ultravox")

        self.assertEqual(credential.api_key, "key-for-session-a")
        self.assertEqual(transport.calls, [("session-a", "ultravox")])


if __name__ == "__main__":
    unittest.main()
