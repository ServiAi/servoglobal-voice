from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.services.ultravox_provider_client import UltravoxProviderClient, UltravoxProviderError

_POST_REQUEST = httpx.Request("POST", "https://api.ultravox.ai/api/voice_preview")
_GET_REQUEST = httpx.Request("GET", "https://api.ultravox.ai/api/accounts/me/tts_api_keys")


def _response(status_code: int, *, content: bytes = b"", headers: dict | None = None, request=_POST_REQUEST) -> httpx.Response:
    return httpx.Response(status_code=status_code, content=content, headers=headers or {}, request=request)


class UltravoxProviderClientPreviewExternalVoiceTests(unittest.TestCase):
    """POST /api/voice_preview generates real (potentially billable) audio,
    so unlike every GET method on this client, it must never retry
    automatically -- see each *_makes_only_one_attempt test below."""

    def setUp(self) -> None:
        self.client = UltravoxProviderClient()
        self.payload = {
            "name": "ServiGlobal External Voice Preview",
            "definition": {"elevenLabs": {"voiceId": "ABC123"}},
        }

    def test_successful_preview_returns_wav_bytes(self) -> None:
        wav = b"RIFF-fake-wav-body"
        with patch("httpx.Client.post", return_value=_response(200, content=wav, headers={"content-type": "audio/wav"})):
            result = self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(result, wav)

    def test_invalid_content_type_raises_provider_invalid_preview(self) -> None:
        with patch("httpx.Client.post", return_value=_response(200, content=b"{}", headers={"content-type": "application/json"})):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_invalid_preview")

    def test_audio_too_large_raises_provider_preview_too_large(self) -> None:
        huge = b"0" * (5 * 1024 * 1024 + 1)
        with patch("httpx.Client.post", return_value=_response(200, content=huge, headers={"content-type": "audio/wav"})):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_preview_too_large")

    def test_400_maps_to_external_voice_preview_failed_without_leaking_the_provider_body(self) -> None:
        with patch("httpx.Client.post", return_value=_response(400, content=b'{"detail": "unknown voiceId, internal secret_note"}')):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "external_voice_preview_failed")
        self.assertNotIn("secret_note", str(ctx.exception))

    def test_401_maps_to_provider_auth_failed(self) -> None:
        with patch("httpx.Client.post", return_value=_response(401)):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_auth_failed")

    def test_403_maps_to_provider_auth_failed(self) -> None:
        with patch("httpx.Client.post", return_value=_response(403)):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_auth_failed")

    def test_429_maps_to_provider_rate_limited(self) -> None:
        with patch("httpx.Client.post", return_value=_response(429)):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_rate_limited")

    def test_5xx_maps_to_provider_unavailable(self) -> None:
        with patch("httpx.Client.post", return_value=_response(503)):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_unavailable")

    def test_timeout_maps_to_provider_unavailable_and_makes_only_one_attempt(self) -> None:
        with patch("httpx.Client.post", side_effect=httpx.ReadTimeout("timed out")) as mock_post:
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(ctx.exception.code, "provider_unavailable")
        self.assertEqual(mock_post.call_count, 1)

    def test_connection_error_makes_only_one_attempt(self) -> None:
        with patch("httpx.Client.post", side_effect=httpx.ConnectError("refused")) as mock_post:
            with self.assertRaises(UltravoxProviderError):
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(mock_post.call_count, 1)

    def test_5xx_response_makes_only_one_attempt_no_retry(self) -> None:
        with patch("httpx.Client.post", return_value=_response(503)) as mock_post:
            with self.assertRaises(UltravoxProviderError):
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(mock_post.call_count, 1)

    def test_rate_limited_response_makes_only_one_attempt_no_retry(self) -> None:
        with patch("httpx.Client.post", return_value=_response(429)) as mock_post:
            with self.assertRaises(UltravoxProviderError):
                self.client.preview_external_voice("key", payload=self.payload)
        self.assertEqual(mock_post.call_count, 1)


class UltravoxProviderClientTtsApiKeysTests(unittest.TestCase):
    def test_returns_parsed_json(self) -> None:
        body = b'{"elevenLabs": {"prefix": "abc"}}'
        with patch(
            "httpx.Client.get",
            return_value=_response(200, content=body, headers={"content-type": "application/json"}, request=_GET_REQUEST),
        ):
            result = UltravoxProviderClient().get_tts_api_keys("key")
        self.assertEqual(result, {"elevenLabs": {"prefix": "abc"}})

    def test_is_idempotent_and_reuses_the_existing_get_retry(self) -> None:
        ok_body = b'{"elevenLabs": {"prefix": "abc"}}'
        responses = [
            _response(503, request=_GET_REQUEST),
            _response(200, content=ok_body, headers={"content-type": "application/json"}, request=_GET_REQUEST),
        ]
        with patch("httpx.Client.get", side_effect=responses) as mock_get, patch("time.sleep"):
            result = UltravoxProviderClient().get_tts_api_keys("key")
        self.assertEqual(result, {"elevenLabs": {"prefix": "abc"}})
        self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
