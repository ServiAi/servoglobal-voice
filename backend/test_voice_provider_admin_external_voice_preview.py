from __future__ import annotations

import unittest
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase
from app.api.auth.deps import get_current_auth_context
from app.db.session import SessionLocal
from app.main import app
from app.models.identity import TenantMembership, User
from app.schemas.integrations import VoiceProviderConfigRequest
from app.services.voice_config_service import VoiceConfigService

_PATH = "/api/v1/integrations/voice/providers/ultravox/external-voice/preview"
_VALID_BODY = {
    "mode": "provider_external", "provider": "elevenlabs", "voice_id": "ABC123",
    "settings": {"model": "eleven_turbo_v2_5", "speed": 1.0},
}


class ExternalVoicePreviewEndpointTests(Integration2ATestCase):
    """POST /providers/{provider}/external-voice/preview -- the "Probar voz"
    action for provider_external + elevenlabs. Backend-only, no frontend
    calls this yet (that's Phase E)."""

    def _configure_ultravox(self, api_key: str = "tenant-a-key") -> None:
        with SessionLocal() as db:
            VoiceConfigService(db).upsert_provider_config(
                self.tenant.id,
                VoiceProviderConfigRequest(provider="ultravox", status="active", api_key=api_key),
            )

    def _as_role(self, role: str) -> None:
        with SessionLocal() as db:
            user = User(email=f"{role}@example.com", name=role, status="active")
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(TenantMembership(tenant_id=self.tenant.id, user_id=user.id, role=role, status="active"))
            db.commit()
            self.user = user

    def test_no_token_returns_401(self) -> None:
        del app.dependency_overrides[get_current_auth_context]
        response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 401)

    def test_tenant_viewer_is_forbidden(self) -> None:
        # Generating audio is potentially billable: only write roles may.
        self._as_role("tenant_viewer")
        response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 403)

    def test_tenant_analyst_is_forbidden(self) -> None:
        self._as_role("tenant_analyst")
        response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 403)

    def test_tenant_admin_can_preview_and_gets_audio_wav_private_no_store(self) -> None:
        self._configure_ultravox()
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            return_value=b"RIFF-preview-bytes",
        ) as mock_preview:
            response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"RIFF-preview-bytes")
        self.assertIn("audio/wav", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        mock_preview.assert_called_once()
        payload = mock_preview.call_args.kwargs["payload"]
        self.assertEqual(payload["name"], "ServiGlobal External Voice Preview")
        self.assertEqual(payload["definition"], {
            "elevenLabs": {"voiceId": "ABC123", "model": "eleven_turbo_v2_5", "speed": 1.0}
        })

    def test_never_exposes_the_ultravox_api_key(self) -> None:
        self._configure_ultravox()
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            return_value=b"RIFF-preview-bytes",
        ):
            response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("x-api-key", {k.lower() for k in response.headers.keys()})
        self.assertNotIn("authorization", {k.lower() for k in response.headers.keys()})

    def test_provider_mode_is_rejected(self) -> None:
        body = {"mode": "provider", "provider": "ultravox", "voice_id": "Mark"}
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=AssertionError("must not call Ultravox for mode=provider on this endpoint"),
        ):
            response = self.client.post(_PATH, json=body)
        self.assertEqual(response.status_code, 422, response.text)

    def test_non_elevenlabs_external_provider_is_rejected(self) -> None:
        body = {"mode": "provider_external", "provider": "cartesia", "voice_id": "x"}
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=AssertionError("must not call Ultravox for an unsupported external provider"),
        ):
            response = self.client.post(_PATH, json=body)
        self.assertEqual(response.status_code, 422, response.text)

    def test_invalid_settings_are_rejected_before_calling_ultravox(self) -> None:
        body = {"mode": "provider_external", "provider": "elevenlabs", "voice_id": "x", "settings": {"pitch": 1}}
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=AssertionError("must not call Ultravox for locally-invalid settings"),
        ):
            response = self.client.post(_PATH, json=body)
        self.assertEqual(response.status_code, 422, response.text)

    def test_missing_model_is_rejected_before_provider_io(self) -> None:
        body = {"mode": "provider_external", "provider": "elevenlabs", "voice_id": "ABC123", "settings": {}}
        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=AssertionError("must not generate a preview without a model"),
        ) as mock_preview:
            response = self.client.post(_PATH, json=body)
        self.assertEqual(response.status_code, 422, response.text)
        mock_preview.assert_not_called()

    def test_secret_like_setting_is_rejected(self) -> None:
        body = {"mode": "provider_external", "provider": "elevenlabs", "voice_id": "x", "settings": {"api_key": "leak"}}
        response = self.client.post(_PATH, json=body)
        self.assertEqual(response.status_code, 422, response.text)

    def test_unknown_provider_path_returns_404(self) -> None:
        response = self.client.post(
            "/api/v1/integrations/voice/providers/elevenlabs/external-voice/preview", json=_VALID_BODY
        )
        self.assertEqual(response.status_code, 404)

    def test_provider_400_response_is_normalized_without_leaking_provider_body(self) -> None:
        self._configure_ultravox()
        from app.services.ultravox_provider_client import UltravoxProviderError

        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=UltravoxProviderError("voice_preview_rejected", 400, reason="model"),
        ):
            response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], {
            "code": "voice_preview_rejected", "reason": "model", "provider": "ultravox",
        })

    def test_preview_rejection_never_exposes_untrusted_reason(self) -> None:
        self._configure_ultravox()
        from app.services.ultravox_provider_client import UltravoxProviderError

        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
            side_effect=UltravoxProviderError("voice_preview_rejected", 400, reason="secret_note"),
        ):
            response = self.client.post(_PATH, json=_VALID_BODY)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["reason"], "other")
        self.assertNotIn("secret_note", response.text)

    def test_non_preview_provider_errors_keep_legacy_string_detail(self) -> None:
        self._configure_ultravox()
        from app.services.ultravox_provider_client import UltravoxProviderError

        for code in ("provider_auth_failed", "provider_rate_limited", "provider_unavailable", "provider_invalid_preview"):
            with self.subTest(code=code), patch(
                "app.services.ultravox_provider_client.UltravoxProviderClient.preview_external_voice",
                side_effect=UltravoxProviderError(code),
            ):
                response = self.client.post(_PATH, json=_VALID_BODY)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], code)

    def test_catalog_preview_rejection_uses_same_contract(self) -> None:
        self._configure_ultravox()
        from app.services.ultravox_provider_client import UltravoxProviderError

        with patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.get_voice_preview",
            side_effect=UltravoxProviderError("voice_preview_rejected", 400, reason="voice"),
        ), patch(
            "app.services.ultravox_provider_client.UltravoxProviderClient.get_voice",
            return_value={"voiceId": "voice-1"},
        ):
            response = self.client.get(
                "/api/v1/integrations/voice/providers/ultravox/voices/voice-1/preview"
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], {
            "code": "voice_preview_rejected", "reason": "voice", "provider": "ultravox",
        })
        self.assertNotIn("voice-1", response.text)


if __name__ == "__main__":
    unittest.main()
