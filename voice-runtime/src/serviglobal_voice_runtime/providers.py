from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .config import Settings
from .contracts import RuntimeSessionSpecV1

EventSender = Callable[..., Awaitable[None]]


class UnsupportedRuntimeProviderError(ValueError):
    pass


class RealtimeProvider(Protocol):
    async def run(self, ctx: Any, spec: RuntimeSessionSpecV1, send_event: EventSender) -> None: ...


def language_hint(language: str) -> str:
    return language.split("-", 1)[0].lower()


def ultravox_options(spec: RuntimeSessionSpecV1, api_key: str) -> dict[str, Any]:
    realtime = spec.runtime.realtime
    if realtime.provider != "ultravox":
        raise UnsupportedRuntimeProviderError("Ultravox runtime requires provider 'ultravox'")
    if not realtime.model.strip():
        raise UnsupportedRuntimeProviderError("Ultravox runtime requires a non-empty execution model")
    configured = realtime.settings
    supported = {"voice", "temperature", "max_duration"}
    unknown = set(configured) - supported
    if unknown:
        raise UnsupportedRuntimeProviderError(f"Unsupported Ultravox settings: {', '.join(sorted(unknown))}")
    temperature = configured.get("temperature")
    if temperature is not None and (not isinstance(temperature, (int, float)) or isinstance(temperature, bool) or not 0 <= temperature <= 1):
        raise UnsupportedRuntimeProviderError("Ultravox temperature must be between 0 and 1")
    prompt_parts = [spec.instructions.system_prompt]
    if spec.instructions.role: prompt_parts.append(f"Role: {spec.instructions.role}")
    if spec.instructions.objective: prompt_parts.append(f"Objective: {spec.instructions.objective}")
    if spec.instructions.closing: prompt_parts.append(f"Closing: {spec.instructions.closing}")
    if spec.behavior.agent_first and spec.instructions.greeting:
        prompt_parts.append(f"Begin with exactly this greeting: {spec.instructions.greeting}")
    options: dict[str, Any] = {
        "model": realtime.model,
        "api_key": api_key,
        "system_prompt": "\n\n".join(filter(None, prompt_parts)),
        "language_hint": language_hint(spec.language),
        "first_speaker": "FIRST_SPEAKER_AGENT" if spec.behavior.agent_first else "FIRST_SPEAKER_USER",
        "enable_greeting_prompt": bool(spec.behavior.agent_first and spec.instructions.greeting),
    }
    for key in supported:
        if key in configured:
            options[key] = configured[key]
    return options


class UltravoxLiveKitRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self, ctx: Any, spec: RuntimeSessionSpecV1, send_event: EventSender) -> None:
        from livekit import rtc
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import ultravox

        options = ultravox_options(spec, self.settings.ULTRAVOX_API_KEY)

        class RuntimeRealtimeSession(ultravox.realtime.RealtimeSession):
            def __init__(self, realtime_model: Any) -> None:
                super().__init__(realtime_model)
                self._provider_session_started = False

            def _handle_ultravox_event(self, event: Any) -> None:
                super()._handle_ultravox_event(event)
                if (
                    isinstance(event, ultravox.realtime.events.CallStartedEvent)
                    and not self._provider_session_started
                ):
                    self._provider_session_started = True
                    asyncio.create_task(self._emit_provider_session_started(event.call_id))

            async def _emit_provider_session_started(self, provider_session_id: str) -> None:
                await send_event(
                    "voice.provider.session.started",
                    source="ultravox",
                    payload={"provider_session_id": provider_session_id},
                )

        class RuntimeRealtimeModel(ultravox.realtime.RealtimeModel):
            def session(self, *, turn_detection_disabled: bool = False) -> RuntimeRealtimeSession:
                session = RuntimeRealtimeSession(realtime_model=self)
                self._sessions.add(session)
                return session

        model = RuntimeRealtimeModel(**options)
        session = AgentSession(llm=model, allow_interruptions=spec.behavior.interruptions != "conservative")
        closed = False
        done = asyncio.Event()
        participant_joined = asyncio.Event()
        connected = False
        input_started = False
        output_started = False
        participant_identities: set[str] = set()

        def is_human(participant: Any) -> bool:
            return participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT

        async def emit_participant_connected(participant: Any) -> None:
            identity = str(participant.identity)
            if identity in participant_identities:
                return
            participant_identities.add(identity)
            participant_joined.set()
            await send_event(
                "voice.participant.connected",
                source="livekit",
                payload={"participant_identity": identity},
            )

        def on_participant_connected(participant: Any) -> None:
            if is_human(participant):
                asyncio.create_task(emit_participant_connected(participant))

        async def emit_input_started() -> None:
            nonlocal input_started
            if input_started:
                return
            input_started = True
            await send_event(
                "voice.audio.input.started",
                source="livekit",
                payload={"track_source": "microphone"},
            )

        def on_track_published(publication: Any, participant: Any) -> None:
            if is_human(participant) and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
                asyncio.create_task(emit_input_started())

        async def close_resources(*, emit_ended: bool, reason: str = "unknown") -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                ctx.room.off("participant_connected", on_participant_connected)
                ctx.room.off("participant_disconnected", on_participant_disconnected)
                ctx.room.off("track_published", on_track_published)
                session.off("user_input_transcribed", on_transcript)
                session.off("agent_state_changed", on_agent_state_changed)
                try:
                    await session.aclose()
                finally:
                    await model.aclose()
                if emit_ended:
                    await send_event("voice.session.ended", payload={"end_reason": reason})
            finally:
                done.set()

        async def cleanup() -> None:
            await close_resources(emit_ended=True, reason="runtime_shutdown")

        ctx.add_shutdown_callback(cleanup)

        async def emit_transcript(event: Any) -> None:
            nonlocal connected
            await emit_input_started()
            await send_event(
                "voice.transcript.final",
                source="livekit",
                payload={"speaker": "user", "text": event.transcript},
            )
            if not connected:
                connected = True
                await send_event("voice.session.connected", source="livekit", payload={})

        def on_transcript(event: Any) -> None:
            if event.is_final:
                asyncio.create_task(emit_transcript(event))

        async def emit_agent_state(event: Any) -> None:
            nonlocal output_started
            if event.new_state == "speaking" and not output_started:
                output_started = True
                await send_event("voice.audio.output.started", source="livekit", payload={})
            elif event.old_state == "speaking" and output_started:
                output_started = False
                await send_event("voice.audio.output.completed", source="livekit", payload={})

        def on_agent_state_changed(event: Any) -> None:
            asyncio.create_task(emit_agent_state(event))

        async def emit_participant_disconnected(participant: Any) -> None:
            identity = str(participant.identity)
            if identity not in participant_identities:
                return
            await send_event(
                "voice.participant.disconnected",
                source="livekit",
                payload={"participant_identity": identity},
            )
            try:
                await close_resources(
                    emit_ended=True,
                    reason="participant_disconnected",
                )
            finally:
                ctx.shutdown("human participant disconnected")

        def on_participant_disconnected(participant: Any) -> None:
            asyncio.create_task(emit_participant_disconnected(participant))

        session.on("user_input_transcribed", on_transcript)
        session.on("agent_state_changed", on_agent_state_changed)
        ctx.room.on("participant_connected", on_participant_connected)
        ctx.room.on("participant_disconnected", on_participant_disconnected)
        ctx.room.on("track_published", on_track_published)

        await send_event("voice.session.started", payload={"livekit_job_id": ctx.job.id})
        try:
            await ctx.connect()
            for participant in ctx.room.remote_participants.values():
                on_participant_connected(participant)
            await session.start(room=ctx.room, agent=Agent(instructions=options["system_prompt"]))
            await send_event("voice.agent.ready", source="livekit", payload={})
            try:
                await asyncio.wait_for(
                    participant_joined.wait(),
                    timeout=self.settings.VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS,
                )
            except TimeoutError:
                await send_event(
                    "voice.session.failed",
                    payload={"error_code": "participant_join_timeout"},
                )
                await close_resources(emit_ended=False)
                ctx.shutdown("participant join timeout")
                return
            await done.wait()
        except Exception:
            await close_resources(emit_ended=False)
            raise


class RealtimeProviderFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve(self, provider: str) -> RealtimeProvider:
        if provider == "ultravox":
            return UltravoxLiveKitRuntime(self.settings)
        raise UnsupportedRuntimeProviderError(f"Runtime provider is not implemented: {provider}")
