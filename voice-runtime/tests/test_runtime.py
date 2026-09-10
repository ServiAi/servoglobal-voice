from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import patch

from serviglobal_voice_runtime.config import Settings
from serviglobal_voice_runtime.contracts import RuntimeSessionSpecV1
from serviglobal_voice_runtime.providers import RealtimeProviderFactory, UnsupportedRuntimeProviderError, language_hint, ultravox_options
from serviglobal_voice_runtime.worker import parse_session_id


def settings() -> Settings:
    return Settings(
        CONTROL_PLANE_BASE_URL="http://control-plane",
        VOICE_RUNTIME_SERVICE_SECRET="x" * 32,
        LIVEKIT_URL="wss://example.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
        ULTRAVOX_API_KEY="ultravox-key",
    )


def spec(*, provider="ultravox", model="fixie-ai/ultravox", **runtime_settings) -> RuntimeSessionSpecV1:
    return RuntimeSessionSpecV1.model_validate({
        "spec_version": "1", "session_id": "session-1", "tenant_id": "tenant-1", "agent_id": "agent-1", "agent_version_id": "version-1",
        "identity": {"name": "Sandra", "description": None},
        "instructions": {"role": "Advisor", "objective": "Help", "system_prompt": "Published prompt", "greeting": "Hola", "closing": "Adios"},
        "behavior": {"response_style": "balanced", "interruptions": "balanced", "turn_detection": "automatic", "confirmation_strategy": "important_data", "agent_first": True},
        "language": "es-CO", "timezone": "America/Bogota",
        "runtime": {"pipeline_type": "realtime", "realtime": {"provider": provider, "model": model, "settings": runtime_settings}},
        "context": {},
    })


class RuntimeTests(unittest.TestCase):
    def test_metadata_contains_only_session_id(self) -> None:
        self.assertEqual(parse_session_id(json.dumps({"session_id": "session-1"})), "session-1")
        with self.assertRaises(ValueError):
            parse_session_id(json.dumps({"session_id": "session-1", "prompt": "secret"}))

    def test_ultravox_mapping(self) -> None:
        options = ultravox_options(spec(voice="Mark", temperature=0.3), "key")
        self.assertEqual(options["model"], "fixie-ai/ultravox")
        self.assertEqual(options["voice"], "Mark")
        self.assertEqual(options["language_hint"], "es")
        self.assertEqual(options["first_speaker"], "FIRST_SPEAKER_AGENT")
        self.assertIn("Published prompt", options["system_prompt"])
        self.assertIn("Hola", options["system_prompt"])

    def test_language_mapping(self) -> None:
        self.assertEqual(language_hint("es-CO"), "es")

    def test_invalid_temperature_and_unknown_provider_fail_closed(self) -> None:
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(temperature=1.1), "key")
        with self.assertRaises(UnsupportedRuntimeProviderError):
            RealtimeProviderFactory(settings()).resolve("openai")

    def test_ultravox_contract_rejects_invalid_provider_and_empty_model(self) -> None:
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(provider="openai"), "key")
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(model=""), "key")

    def test_contract_rejects_secret_context(self) -> None:
        data = spec().model_dump()
        data["context"] = {"nested": {"api_key": "must-not-pass"}}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)


class UltravoxLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_connects_before_starting_session(self) -> None:
        from serviglobal_voice_runtime.providers import UltravoxLiveKitRuntime

        order = []
        events = []
        started = asyncio.Event()
        closed = {"model": 0, "session": 0}
        sessions = []

        class FakeModel:
            def __init__(self, **options):
                self.options = options

            async def aclose(self):
                closed["model"] += 1

        class FakeSession:
            def __init__(self, **kwargs):
                self.handlers = {}
                sessions.append(self)

            def on(self, event_name, callback=None):
                if callback is None:
                    return lambda decorated: self.on(event_name, decorated)
                self.handlers[event_name] = callback
                return callback

            def off(self, event_name, callback):
                if self.handlers.get(event_name) is callback:
                    del self.handlers[event_name]

            def emit(self, event_name, event):
                self.handlers[event_name](event)

            async def start(self, **kwargs):
                order.append("start")
                started.set()

            async def aclose(self):
                closed["session"] += 1

        class FakeAgent:
            def __init__(self, **kwargs):
                pass

        class FakeRoom:
            def __init__(self):
                self.handlers = {}
                self.remote_participants = {}

            def on(self, event_name, callback):
                self.handlers[event_name] = callback

            def off(self, event_name, callback):
                if self.handlers.get(event_name) is callback:
                    del self.handlers[event_name]

            def emit(self, event_name, *args):
                self.handlers[event_name](*args)

        class FakeContext:
            job = types.SimpleNamespace(id="job-1")
            shutdown_callback = None

            def __init__(self):
                self.room = FakeRoom()
                self.shutdown_reasons = []

            def add_shutdown_callback(self, callback):
                self.shutdown_callback = callback

            async def connect(self):
                order.append("connect")

            def shutdown(self, reason):
                self.shutdown_reasons.append(reason)

        livekit = types.ModuleType("livekit")
        agents = types.ModuleType("livekit.agents")
        plugins = types.ModuleType("livekit.plugins")
        agents.Agent = FakeAgent
        agents.AgentSession = FakeSession
        plugins.ultravox = types.SimpleNamespace(
            realtime=types.SimpleNamespace(RealtimeModel=FakeModel)
        )
        livekit.rtc = types.SimpleNamespace(
            ParticipantKind=types.SimpleNamespace(PARTICIPANT_KIND_AGENT=4),
            TrackSource=types.SimpleNamespace(SOURCE_MICROPHONE=2),
        )
        livekit.agents = agents
        livekit.plugins = plugins
        ctx = FakeContext()

        async def send_event(event_type, **kwargs):
            events.append((event_type, kwargs))

        with patch.dict(
            sys.modules,
            {"livekit": livekit, "livekit.agents": agents, "livekit.plugins": plugins},
        ):
            task = asyncio.create_task(
                UltravoxLiveKitRuntime(settings()).run(ctx, spec(), send_event)
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertEqual(order, ["connect", "start"])
            await asyncio.sleep(0)
            self.assertIn("voice.agent.ready", [event[0] for event in events])
            self.assertNotIn("voice.session.connected", [event[0] for event in events])

            participant = types.SimpleNamespace(identity="web-random", kind=0)
            ctx.room.emit("participant_connected", participant)
            ctx.room.emit(
                "track_published",
                types.SimpleNamespace(source=2),
                participant,
            )
            sessions[0].emit(
                "user_input_transcribed",
                types.SimpleNamespace(is_final=True, transcript="Hola Sandra"),
            )
            sessions[0].emit(
                "agent_state_changed",
                types.SimpleNamespace(old_state="thinking", new_state="speaking"),
            )
            sessions[0].emit(
                "agent_state_changed",
                types.SimpleNamespace(old_state="speaking", new_state="listening"),
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            event_names = [event[0] for event in events]
            self.assertIn("voice.participant.connected", event_names)
            self.assertIn("voice.audio.input.started", event_names)
            self.assertIn("voice.transcript.final", event_names)
            self.assertIn("voice.session.connected", event_names)
            self.assertIn("voice.audio.output.started", event_names)
            self.assertIn("voice.audio.output.completed", event_names)
            self.assertLess(
                event_names.index("voice.transcript.final"),
                event_names.index("voice.session.connected"),
            )

            ctx.room.emit("participant_disconnected", participant)
            await asyncio.wait_for(task, timeout=1)
            await ctx.shutdown_callback()
            await ctx.shutdown_callback()
            self.assertEqual(closed, {"model": 1, "session": 1})
            self.assertIn("voice.participant.disconnected", [event[0] for event in events])
            self.assertIn("voice.session.ended", [event[0] for event in events])
            self.assertEqual(ctx.shutdown_reasons, ["human participant disconnected"])


if __name__ == "__main__":
    unittest.main()
