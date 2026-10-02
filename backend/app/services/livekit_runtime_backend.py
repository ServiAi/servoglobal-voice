"""TEMPORARY compatibility shim -- moved to `app.modules.voice.infrastructure.livekit_runtime`.

Aliases this legacy path to the real module (same object: no duplicated
logic, and unittest.mock.patch targets keep working). Kept only for legacy
consumers that are not migrated yet (Telephony: outbound_voice_call_service,
voice_session_sip_service; legacy calls: voice_call_service; scripts). New
code must use app.modules.voice.public. Retirement is tracked in
docs/architecture/MODULAR_MONOLITH_MIGRATION.md.
"""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("app.modules.voice.infrastructure.livekit_runtime")
