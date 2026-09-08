# ServiGlobal Voice Runtime

Independent realtime data plane. It receives LiveKit jobs containing only a `session_id`, fetches `RuntimeSessionSpecV1` from the Control Plane with a short-lived service JWT, and runs Ultravox through the official LiveKit plugin. It never connects to the Control Plane database.

Run with `python -m serviglobal_voice_runtime.main start`. LiveKit AgentServer provides readiness at `/` on port `8081`.
