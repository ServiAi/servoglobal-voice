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
    configured = spec.runtime.realtime.settings
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
        "model": spec.runtime.realtime.model,
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
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import ultravox

        options = ultravox_options(spec, self.settings.ULTRAVOX_API_KEY)
        model = ultravox.realtime.RealtimeModel(**options)
        session = AgentSession(llm=model, allow_interruptions=spec.behavior.interruptions != "conservative")
        closed = False
        done = asyncio.Event()

        async def close_resources(*, emit_ended: bool) -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                await session.aclose()
                await model.aclose()
                if emit_ended:
                    await send_event("voice.session.ended", payload={"end_reason": "unknown"})
            finally:
                done.set()

        async def cleanup() -> None:
            await close_resources(emit_ended=True)

        ctx.add_shutdown_callback(cleanup)

        @session.on("user_input_transcribed")
        def on_transcript(event: Any) -> None:
            if event.is_final:
                asyncio.create_task(send_event("voice.transcript.final", source="livekit", payload={"speaker": "user", "text": event.transcript}))

        await send_event("voice.session.started", payload={"livekit_job_id": ctx.job.id})
        try:
            await session.start(room=ctx.room, agent=Agent(instructions=options["system_prompt"]))
            await ctx.connect()
            await send_event("voice.session.connected", payload={})
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
