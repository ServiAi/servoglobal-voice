# ServiGlobal Voice Runtime

Independent realtime data plane. It receives LiveKit jobs containing only a `session_id`, fetches `RuntimeSessionSpecV1` from the Control Plane with a short-lived service JWT, and runs Ultravox through the official LiveKit plugin. It never connects to the Control Plane database.

Provider credentials (e.g. the tenant's Ultravox API key) are never stored or configured in this runtime. Each job resolves its credential dynamically from the Control Plane, scoped to the job's `session_id` and provider, through `ControlPlaneCredentialResolver` (`credentials.py`). The Control Plane looks up the `VoiceSession`, derives its tenant, and returns the decrypted key for that tenant's active integration — so two tenants running Ultravox concurrently always get their own key. The resolved key lives only in memory for the duration of the job; it is never persisted, cached to disk, or included in `RuntimeSessionSpecV1`, LiveKit metadata, tokens, events, or logs.

Run with `python -m serviglobal_voice_runtime.main start`. LiveKit AgentServer provides readiness at `/` on port `8081`.

The worker waits at most `VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS` (default `60`) for a non-agent participant. Browser participants join the dispatch room with a short-lived, room-scoped token and publish microphone audio only.
