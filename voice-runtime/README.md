# ServiGlobal Voice Runtime

Independent realtime data plane. It receives LiveKit jobs containing only a `session_id`, fetches `RuntimeSessionSpecV1` from the Control Plane with a short-lived service JWT, and runs Ultravox through the official LiveKit plugin. It never connects to the Control Plane database.

Run with `python -m serviglobal_voice_runtime.main start`. LiveKit AgentServer provides readiness at `/` on port `8081`.

The worker waits at most `VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS` (default `60`) for a non-agent participant. Browser participants join the dispatch room with a short-lived, room-scoped token and publish microphone audio only.
