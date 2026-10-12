"""Read-only gate: are there still ACTIVE provider-originated (legacy) voice calls?

Run it before deploying the release that retires the legacy voice runtime (PR #137). It counts the
calls that only the legacy runtime could still be driving and never writes, retries, promotes or
terminates anything. Output is technical only (category, count, row id, status): never phones,
emails, names, prompts, tokens or provider payloads.

    DATABASE_URL=postgresql+psycopg://... python scripts/check_legacy_voice_runtime_drain.py

Exit code: 0 = nothing active (SAFE TO DEPLOY), 1 = legacy calls still active
(LEGACY VOICE RUNTIME NOT DRAINED), 2 = could not run.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

SAMPLE_LIMIT = 20

# category -> (table, SQL condition). Every condition is explicit and conservative; canonical calls
# (provider livekit_sip, or any call backed by a VoiceSession launch) never match.
CATEGORIES: dict[str, tuple[str, str]] = {
    "legacy_public_webrtc_runtime": (
        "tenant_voice_runtime_calls",
        "launch_runtime = 'legacy_provider' "
        "AND status IN ('reserved', 'starting', 'ready', 'connected', 'unknown')",
    ),
    "legacy_voice_experience_callbacks": (
        "crm_voice_calls",
        "origin = 'legacy_voice_experience_callback' "
        "AND status IN ('requested', 'starting', 'queued', 'ringing', 'in_progress', 'dialing')",
    ),
    # Provider-originated CRM outbound (and callbacks written by a pre-origin replica, which default
    # to crm_outbound): an outbound call whose provider is not the canonical SIP transport.
    "legacy_provider_originated_outbound": (
        "crm_voice_calls",
        "origin = 'crm_outbound' AND direction = 'outbound' AND provider <> 'livekit_sip' "
        "AND status IN ('requested', 'starting', 'queued', 'ringing', 'in_progress', 'dialing')",
    ),
}


def active_legacy_calls(connection) -> dict[str, list[tuple[str, str]]]:
    """category -> [(row id, status)] for every active legacy call (read-only)."""
    result: dict[str, list[tuple[str, str]]] = {}
    for category, (table, condition) in CATEGORIES.items():
        rows = connection.execute(text(f"SELECT id, status FROM {table} WHERE {condition} ORDER BY id")).all()
        result[category] = [(row[0], row[1]) for row in rows]
    return result


def main(argv: list[str] | None = None) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            found = active_legacy_calls(connection)
    except Exception as exc:  # noqa: BLE001 - an operational tool: report and exit 2
        print(f"Could not run the drain check: {type(exc).__name__}", file=sys.stderr)
        return 2
    total = sum(len(rows) for rows in found.values())
    for category, rows in found.items():
        print(f"{category}: {len(rows)}")
        for row_id, status in rows[:SAMPLE_LIMIT]:
            print(f"  - {row_id} status={status}")
        if len(rows) > SAMPLE_LIMIT:
            print(f"  ... and {len(rows) - SAMPLE_LIMIT} more")
    if total:
        print(f"LEGACY VOICE RUNTIME NOT DRAINED ({total} active). Wait or reconcile, then run it again.")
        return 1
    print("SAFE TO DEPLOY: no active legacy voice calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
