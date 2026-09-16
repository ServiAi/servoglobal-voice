from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch
import wave

import httpx

from app.services.ultravox_provider_client import UltravoxProviderClient, UltravoxProviderError

_POST_REQUEST = httpx.Request("POST", "https://api.ultravox.ai/api/voice_preview")
_GET_REQUEST = httpx.Request("GET", "https://api.ultravox.ai/api/accounts/me/tts_api_keys")
_GET_PREVIEW_REQUEST = httpx.Request("GET", "https://api.ultravox.ai/api/voices/voice-1/preview")


def _wav() -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00")
    return buffer.getvalue()


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


class UltravoxProviderClientCatalogPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = UltravoxProviderClient()
        self.wav = _wav()

    def test_accepts_real_wav_even_when_mime_is_octet_stream(self) -> None:
        response = _response(200, content=self.wav, headers={"content-type": "application/octet-stream"},
                             request=_GET_PREVIEW_REQUEST)
        with patch("httpx.Client.get", return_value=response):
            self.assertEqual(self.client.get_voice_preview("key", "voice-1"), self.wav)

    def test_rejects_json_even_when_mime_claims_wav_without_leaking_body(self) -> None:
        response = _response(200, content=b'{"secret": "do-not-log"}', headers={"content-type": "audio/wav"},
                             request=_GET_PREVIEW_REQUEST)
        with patch("httpx.Client.get", return_value=response), self.assertLogs(
                "app.services.ultravox_provider_client", level="WARNING") as logs:
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.get_voice_preview("key", "voice-1")
        self.assertEqual(ctx.exception.code, "provider_invalid_preview")
        self.assertNotIn("secret", " ".join(logs.output))
        self.assertNotIn("key", " ".join(logs.output))

    def test_follows_same_api_origin_redirect_with_key(self) -> None:
        redirect = _response(302, headers={"location": "/api/media/sample"}, request=_GET_PREVIEW_REQUEST)
        final = _response(200, content=self.wav, headers={"content-type": "audio/wav"},
                          request=httpx.Request("GET", "https://api.ultravox.ai/api/media/sample"))
        with patch("httpx.Client.get", side_effect=[redirect, final]) as get:
            self.assertEqual(self.client.get_voice_preview("key", "voice-1"), self.wav)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].kwargs["headers"]["X-API-Key"], "key")

    def test_follows_ultravox_cdn_redirect_without_forwarding_key(self) -> None:
        redirect = _response(302, headers={"location": "https://media.ultravox.ai/sample.wav"},
                             request=_GET_PREVIEW_REQUEST)
        final = _response(200, content=self.wav, headers={"content-type": "audio/x-wav"},
                          request=httpx.Request("GET", "https://media.ultravox.ai/sample.wav"))
        with patch("httpx.Client.get", side_effect=[redirect, final]) as get:
            self.assertEqual(self.client.get_voice_preview("key", "voice-1"), self.wav)
        self.assertEqual(get.call_args_list[1].kwargs["headers"], {})

    def test_follows_google_storage_audio_redirect_without_forwarding_key(self) -> None:
        redirect = _response(302, headers={"location": "https://storage.googleapis.com/sample-bucket/sample.wav"},
                             request=_GET_PREVIEW_REQUEST)
        final = _response(200, content=self.wav, headers={"content-type": "application/octet-stream"},
                          request=httpx.Request("GET", "https://storage.googleapis.com/sample-bucket/sample.wav"))
        with patch("httpx.Client.get", side_effect=[redirect, final]) as get:
            self.assertEqual(self.client.get_voice_preview("key", "voice-1"), self.wav)
        self.assertEqual(get.call_args_list[1].kwargs["headers"], {})

    def test_blocks_other_domain_redirect_without_key_or_url_in_logs(self) -> None:
        redirect = _response(302, headers={"location": "https://example.invalid/private?token=secret"},
                             request=_GET_PREVIEW_REQUEST)
        with patch("httpx.Client.get", return_value=redirect) as get, self.assertLogs(
                "app.services.ultravox_provider_client", level="WARNING") as logs:
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.get_voice_preview("key", "voice-1")
        self.assertEqual(ctx.exception.code, "provider_preview_redirect_blocked")
        self.assertEqual(get.call_count, 1)
        self.assertNotIn("token=secret", " ".join(logs.output))
        self.assertNotIn("example.invalid", " ".join(logs.output))

    def test_redirect_hops_are_bounded(self) -> None:
        redirects = [_response(302, headers={"location": "/next"}, request=_GET_PREVIEW_REQUEST)]
        redirects.extend(_response(302, headers={"location": "/next"},
                                   request=httpx.Request("GET", "https://api.ultravox.ai/next")) for _ in range(2))
        with patch("httpx.Client.get", side_effect=redirects) as get, self.assertLogs(
                "app.services.ultravox_provider_client", level="WARNING"):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.get_voice_preview("key", "voice-1")
        self.assertEqual(ctx.exception.code, "provider_preview_redirect_blocked")
        self.assertEqual(get.call_count, 3)

    def test_redirect_network_failure_is_sanitized(self) -> None:
        redirect = _response(302, headers={"location": "https://media.ultravox.ai/sample.wav"},
                             request=_GET_PREVIEW_REQUEST)
        with patch("httpx.Client.get", side_effect=[redirect, httpx.ConnectError("network failed")]):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.get_voice_preview("key", "voice-1")
        self.assertEqual(ctx.exception.code, "provider_unavailable")

    def test_large_wav_is_rejected(self) -> None:
        response = _response(200, content=self.wav + b"0" * (5 * 1024 * 1024),
                             headers={"content-type": "audio/wav"}, request=_GET_PREVIEW_REQUEST)
        with patch("httpx.Client.get", return_value=response):
            with self.assertRaises(UltravoxProviderError) as ctx:
                self.client.get_voice_preview("key", "voice-1")
        self.assertEqual(ctx.exception.code, "provider_preview_too_large")


if __name__ == "__main__":
    unittest.main()
