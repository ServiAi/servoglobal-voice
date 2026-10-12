"""The read-only gate operators run before deploying the legacy-runtime retirement."""

from __future__ import annotations

import contextlib
import io
import os
from unittest.mock import patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal, engine
from app.modules.crm.infrastructure.models import CrmVoiceCall
from app.modules.voice_experiences.infrastructure.submission_models import TenantVoiceRuntimeCall
from scripts.check_legacy_voice_runtime_drain import active_legacy_calls, main

PHONE = "+573001112233"


class LegacyDrainGateTests(Integration2ATestCase):
    def _crm(self, **values) -> str:
        with SessionLocal() as db:
            row = CrmVoiceCall(
                tenant_id=self.tenant.id,
                provider=values.pop("provider", "ultravox"),
                origin=values.pop("origin", "crm_outbound"),
                direction=values.pop("direction", "outbound"),
                status=values.pop("status", "requested"),
                to_phone=PHONE,
                **values,
            )
            db.add(row)
            db.commit()
            return row.id

    def _runtime(self, launch_runtime: str, status: str) -> str:
        with SessionLocal() as db:
            row = TenantVoiceRuntimeCall(
                tenant_id=self.tenant.id,
                context_session_id=f"ctx-{launch_runtime}-{status}",
                submission_id="submission",
                experience_id="experience",
                experience_version_id="version",
                agent_config_id="agent-config",
                crm_voice_call_id=f"crm-{launch_runtime}-{status}",
                launch_runtime=launch_runtime,
                status=status,
            )
            db.add(row)
            db.commit()
            return row.id

    def _run_main(self) -> tuple[int, str]:
        output = io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": str(engine.url.render_as_string(hide_password=False))}):
            with contextlib.redirect_stdout(output):
                code = main()
        return code, output.getvalue()

    def test_nothing_active_is_safe_to_deploy(self) -> None:
        self._runtime("legacy_provider", "ended")  # history, not in flight
        self._crm(origin="legacy_voice_experience_callback", status="completed")
        code, output = self._run_main()
        self.assertEqual(code, 0, output)
        self.assertIn("SAFE TO DEPLOY", output)

    def test_every_active_legacy_call_blocks_the_deploy_and_canonical_calls_never_do(self) -> None:
        legacy_runtime = self._runtime("legacy_provider", "starting")
        legacy_callback = self._crm(origin="legacy_voice_experience_callback", status="queued")
        provider_outbound = self._crm(status="in_progress")
        canonical = [
            self._runtime("canonical_voice_session", "ready"),
            self._crm(origin="voice_experience_callback", provider="livekit_sip", status="dialing"),
            self._crm(provider="livekit_sip", status="in_progress"),  # CRM outbound over LiveKit SIP
            self._crm(provider="ultravox", direction="webrtc", status="requested"),  # canonical public WebRTC call
        ]
        with SessionLocal() as db:
            before = db.query(CrmVoiceCall).count(), db.query(TenantVoiceRuntimeCall).count()

        with SessionLocal() as db:
            found = active_legacy_calls(db.connection())
        code, output = self._run_main()

        self.assertEqual({k: [row_id for row_id, _ in v] for k, v in found.items()}, {
            "legacy_public_webrtc_runtime": [legacy_runtime],
            "legacy_voice_experience_callbacks": [legacy_callback],
            "legacy_provider_originated_outbound": [provider_outbound],
        })
        self.assertEqual(code, 1)
        self.assertIn("LEGACY VOICE RUNTIME NOT DRAINED (3 active)", output)
        for row_id in (legacy_runtime, legacy_callback, provider_outbound):
            self.assertIn(row_id, output)
        for row_id in canonical:
            self.assertNotIn(row_id, output)
        self.assertNotIn(PHONE, output)  # technical identifiers only, never PII
        with SessionLocal() as db:  # read-only: nothing was written, promoted or terminated
            self.assertEqual((db.query(CrmVoiceCall).count(), db.query(TenantVoiceRuntimeCall).count()), before)
            self.assertEqual(db.scalars(select(TenantVoiceRuntimeCall.status).where(TenantVoiceRuntimeCall.id == legacy_runtime)).one(), "starting")

    def test_it_cannot_run_without_a_database(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(), 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
