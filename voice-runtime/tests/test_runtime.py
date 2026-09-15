from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import patch

from serviglobal_voice_runtime.config import Settings
from serviglobal_voice_runtime.contracts import AgentVoiceConfig, RuntimeSessionSpecV1
from serviglobal_voice_runtime.credentials import ProviderCredential
from serviglobal_voice_runtime.providers import RealtimeProviderFactory, UnsupportedRuntimeProviderError, build_elevenlabs_external_voice, language_hint, ultravox_options
from serviglobal_voice_runtime.worker import parse_session_id


def settings() -> Settings:
    return Settings(
        CONTROL_PLANE_BASE_URL="http://control-plane",
        VOICE_RUNTIME_SERVICE_SECRET="x" * 32,
        LIVEKIT_URL="wss://example.livekit.cloud",
        LIVEKIT_API_KEY="key",
        LIVEKIT_API_SECRET="secret",
    )


class FakeCredentialResolver:
    """Stands in for ControlPlaneCredentialResolver: no HTTP, no Control Plane."""

    def __init__(self, credential: ProviderCredential) -> None:
        self.credential = credential
        self.calls: list[tuple[str, str]] = []

    async def resolve(self, *, session_id: str, provider: str) -> ProviderCredential:
        self.calls.append((session_id, provider))
        return self.credential


def spec(*, provider="ultravox", model="fixie-ai/ultravox", runtime_voice=None, **runtime_settings) -> RuntimeSessionSpecV1:
    return RuntimeSessionSpecV1.model_validate({
        "spec_version": "1", "session_id": "session-1", "tenant_id": "tenant-1", "agent_id": "agent-1", "agent_version_id": "version-1",
        "identity": {"name": "Sandra", "description": None},
        "instructions": {"role": "Advisor", "objective": "Help", "system_prompt": "Published prompt", "greeting": "Hola", "closing": "Adios"},
        "behavior": {"response_style": "balanced", "interruptions": "balanced", "turn_detection": "automatic", "confirmation_strategy": "important_data", "agent_first": True},
        "language": "es-CO", "timezone": "America/Bogota",
        "runtime": {"pipeline_type": "realtime", "realtime": {"provider": provider, "model": model, "settings": runtime_settings, "voice": runtime_voice}},
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

    def test_provider_voice_overrides_legacy_voice(self) -> None:
        options = ultravox_options(
            spec(
                runtime_voice={"mode": "provider", "provider": "ultravox", "voice_id": "NEW_VOICE"},
                voice="LEGACY_VOICE", temperature=0.3, max_duration="10m",
            ),
            "key",
        )
        self.assertEqual(options["voice"], "NEW_VOICE")
        self.assertEqual(options["temperature"], 0.3)
        self.assertEqual(options["max_duration"], "10m")

    def test_no_voice_uses_plugin_default(self) -> None:
        self.assertNotIn("voice", ultravox_options(spec(), "key"))

    def test_elevenlabs_mapper_full_and_minimal(self) -> None:
        full = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="ABC123",
            settings={"model": "eleven_turbo_v2_5", "speed": 1.0, "stability": 0.8,
                      "similarity_boost": 0.75, "use_speaker_boost": True},
        )
        self.assertEqual(build_elevenlabs_external_voice(full), {
            "elevenLabs": {"voiceId": "ABC123", "model": "eleven_turbo_v2_5", "speed": 1.0,
                           "stability": 0.8, "similarityBoost": 0.75, "useSpeakerBoost": True},
        })
        minimal = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="ABC123",
            settings={"model": "future_model"},
        )
        self.assertEqual(build_elevenlabs_external_voice(minimal), {
            "elevenLabs": {"voiceId": "ABC123", "model": "future_model"},
        })

    def test_provider_external_ignores_legacy_voice(self) -> None:
        options = ultravox_options(spec(
            runtime_voice={"mode": "provider_external", "provider": "elevenlabs",
                           "voice_id": "ABC123", "settings": {"model": "future_model"}},
            voice="LEGACY_VOICE",
        ), "key")
        self.assertEqual(options["external_voice"], {
            "elevenLabs": {"voiceId": "ABC123", "model": "future_model"},
        })
        self.assertNotIn("voice", options)

    def test_invalid_elevenlabs_external_voice_fails_closed(self) -> None:
        cases = (
            ("cartesia", "ABC123", {"model": "future_model"}),
            ("elevenlabs", " ", {"model": "future_model"}),
            ("elevenlabs", "ABC123", {}),
            ("elevenlabs", "ABC123", {"model": " "}),
            ("elevenlabs", "ABC123", {"model": "future_model", "foo": "bar"}),
            ("elevenlabs", "ABC123", {"model": "future_model", "speed": True}),
            ("elevenlabs", "ABC123", {"model": "future_model", "speed": 0.6}),
            ("elevenlabs", "ABC123", {"model": "future_model", "speed": float("nan")}),
            ("elevenlabs", "ABC123", {"model": "future_model", "stability": "high"}),
            ("elevenlabs", "ABC123", {"model": "future_model", "stability": 1.1}),
            ("elevenlabs", "ABC123", {"model": "future_model", "stability": float("inf")}),
            ("elevenlabs", "ABC123", {"model": "future_model", "similarity_boost": True}),
            ("elevenlabs", "ABC123", {"model": "future_model", "similarity_boost": -0.1}),
            ("elevenlabs", "ABC123", {"model": "future_model", "use_speaker_boost": "yes"}),
        )
        for provider, voice_id, voice_settings in cases:
            with self.subTest(provider=provider, voice_id=voice_id, settings=voice_settings):
                with self.assertRaises(UnsupportedRuntimeProviderError):
                    ultravox_options(spec(runtime_voice={
                        "mode": "provider_external", "provider": provider,
                        "voice_id": voice_id, "settings": voice_settings,
                    }), "key")

    def test_elevenlabs_mapper_rejects_secret_like_setting_after_validation(self) -> None:
        voice = AgentVoiceConfig(
            mode="provider_external", provider="elevenlabs", voice_id="ABC123",
            settings={"model": "future_model"},
        )
        voice.settings["api_key"] = "do-not-log"
        with self.assertRaises(UnsupportedRuntimeProviderError) as caught:
            build_elevenlabs_external_voice(voice)
        self.assertNotIn("do-not-log", str(caught.exception))

    def test_invalid_provider_voice_fails_closed(self) -> None:
        for provider, voice_id in (("elevenlabs", "voice"), ("ultravox", " ")):
            with self.subTest(provider=provider, voice_id=voice_id):
                with self.assertRaises(UnsupportedRuntimeProviderError):
                    ultravox_options(
                        spec(runtime_voice={"mode": "provider", "provider": provider, "voice_id": voice_id}),
                        "key",
                    )

    def test_language_mapping(self) -> None:
        self.assertEqual(language_hint("es-CO"), "es")

    def test_invalid_temperature_and_unknown_provider_fail_closed(self) -> None:
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(temperature=1.1), "key")
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(unknown_setting=True), "key")
        resolver = FakeCredentialResolver(ProviderCredential(provider="ultravox", api_key="key"))
        with self.assertRaises(UnsupportedRuntimeProviderError):
            RealtimeProviderFactory(settings(), resolver, None).resolve("openai")

    def test_ultravox_contract_rejects_invalid_provider_and_empty_model(self) -> None:
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(provider="openai"), "key")
        with self.assertRaises(UnsupportedRuntimeProviderError):
            ultravox_options(spec(model=""), "key")

    def test_contract_rejects_secret_context(self) -> None:
        data = spec().model_dump()
        data["context"] = {"variables": {"nested": {"api_key": "must-not-pass"}}}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)

    def test_context_accepts_the_exact_session_context_shape_the_backend_emits(self) -> None:
        # Parity check against backend/app/schemas/session_context.py::SessionContextV1
        # -- see ContactResolutionService for the producing side.
        data = spec().model_dump()
        data["context"] = {
            "schema_version": "1",
            "source": "outbound",
            "caller": {"phone": "+573001234567"},
            "contact": {"id": "contact_1", "name": "Carlos Pérez", "phone": "+573001234567", "email": None},
            "lead": {"id": "lead_1", "status": "open", "stage": "qualified"},
            "campaign": {"name": "Cobranza septiembre"},
            "variables": {"debt_amount": 850000},
        }
        parsed = RuntimeSessionSpecV1.model_validate(data)
        self.assertEqual(parsed.context.contact.name, "Carlos Pérez")
        self.assertEqual(parsed.context.lead.status, "open")
        self.assertEqual(parsed.context.variables, {"debt_amount": 850000})

    def test_context_rejects_a_bare_lead_id_top_level_key(self) -> None:
        # Proves the mirror stays as strict as the backend contract: no
        # arbitrary top-level identity keys, only the typed sub-contexts.
        data = spec().model_dump()
        data["context"] = {"lead_id": "lead-9"}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)

    def test_context_defaults_to_empty_for_backward_compatibility(self) -> None:
        self.assertEqual(spec().context.variables, {})
        self.assertIsNone(spec().context.caller)

    def test_contract_rejects_unregistered_overrides_and_secret_extensions(self) -> None:
        data = spec().model_dump()
        data["runtime"]["realtime"]["provider_overrides"] = {"selectedTools": []}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)
        data = spec().model_dump()
        data["runtime"]["realtime"]["provider_extensions"] = {"sharedSecrets": {}}
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)

    def test_settings_do_not_require_a_global_ultravox_api_key(self) -> None:
        self.assertFalse(hasattr(settings(), "ULTRAVOX_API_KEY"))

    def test_contract_accepts_the_exact_compiled_tool_spec_shape_the_backend_emits(self) -> None:
        # Parity check against backend/app/schemas/runtime_session.py::CompiledToolSpec
        # (key/name/description/input_schema, no `config`, no handler
        # reference) -- see AgentCompilerService for the producing side.
        data = spec().model_dump()
        data["tools"] = [{
            "key": "calendar.check_availability",
            "name": "Consultar disponibilidad",
            "description": "Consulta franjas horarias disponibles.",
            "input_schema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]},
        }]
        parsed = RuntimeSessionSpecV1.model_validate(data)
        self.assertEqual(len(parsed.tools), 1)
        self.assertEqual(parsed.tools[0].key, "calendar.check_availability")

    def test_contract_rejects_a_tool_binding_config_field_leaking_through(self) -> None:
        # config never belongs in the compiled spec -- proves the mirror
        # stays as strict as the backend contract on this field.
        data = spec().model_dump()
        data["tools"] = [{
            "key": "whatsapp.send_message", "name": "x", "description": "x",
            "input_schema": {"type": "object", "properties": {}},
            "config": {"template_key": "should-not-be-here"},
        }]
        with self.assertRaises(ValueError):
            RuntimeSessionSpecV1.model_validate(data)

    def test_tools_defaults_to_empty_list_for_backward_compatibility(self) -> None:
        self.assertEqual(spec().tools, [])


class UltravoxCredentialResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_livekit_constructor_receives_external_voice_without_legacy_voice(self) -> None:
        from livekit.plugins import ultravox
        from serviglobal_voice_runtime.providers import UltravoxLiveKitRuntime

        class ConstructionStopped(Exception):
            pass

        resolver = FakeCredentialResolver(ProviderCredential(provider="ultravox", api_key="tenant-key"))
        runtime = UltravoxLiveKitRuntime(settings(), resolver, None)
        external_spec = spec(
            runtime_voice={"mode": "provider_external", "provider": "elevenlabs",
                           "voice_id": "ABC123", "settings": {"model": "future_model"}},
            voice="LEGACY_VOICE",
        )
        with patch.object(ultravox.realtime.RealtimeModel, "__init__", side_effect=ConstructionStopped) as init:
            with self.assertRaises(ConstructionStopped):
                await runtime.run(None, external_spec, lambda *args, **kwargs: None)
        self.assertEqual(init.call_args.kwargs["external_voice"], {
            "elevenLabs": {"voiceId": "ABC123", "model": "future_model"},
        })
        self.assertNotIn("voice", init.call_args.kwargs)
        self.assertEqual(resolver.calls, [("session-1", "ultravox")])

    async def test_ultravox_requires_a_resolved_session_id(self) -> None:
        from serviglobal_voice_runtime.providers import UltravoxLiveKitRuntime

        data = spec().model_dump()
        data["session_id"] = None
        session_less_spec = RuntimeSessionSpecV1.model_validate(data)
        resolver = FakeCredentialResolver(ProviderCredential(provider="ultravox", api_key="tenant-key"))
        runtime = UltravoxLiveKitRuntime(settings(), resolver, None)

        with self.assertRaises(UnsupportedRuntimeProviderError):
            await runtime.run(None, session_less_spec, lambda *args, **kwargs: None)
        self.assertEqual(resolver.calls, [])

    async def test_ultravox_never_falls_back_to_a_global_credential(self) -> None:
        from serviglobal_voice_runtime.providers import UltravoxLiveKitRuntime

        class ExplodingCredentialResolver:
            async def resolve(self, *, session_id: str, provider: str) -> ProviderCredential:
                raise AssertionError("must not be reached for this test setup")

        # Constructing the runtime and settings requires no ULTRAVOX_API_KEY anywhere.
        runtime = UltravoxLiveKitRuntime(settings(), ExplodingCredentialResolver(), None)
        self.assertFalse(hasattr(runtime.settings, "ULTRAVOX_API_KEY"))


class UltravoxLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_connects_before_starting_session(self) -> None:
        from serviglobal_voice_runtime.providers import UltravoxLiveKitRuntime

        order = []
        events = []
        started = asyncio.Event()
        closed = {"model": 0, "session": 0}
        sessions = []
        realtime_sessions = []
        handled_ultravox_events = []

        class FakeCallStartedEvent:
            def __init__(self, call_id):
                self.call_id = call_id

        class FakeRealtimeSession:
            def __init__(self, realtime_model):
                self.realtime_model = realtime_model
                realtime_sessions.append(self)

            def _handle_ultravox_event(self, event):
                handled_ultravox_events.append(event)

        class FakeModel:
            def __init__(self, **options):
                self.options = options
                self._sessions = set()

            async def aclose(self):
                closed["model"] += 1

        class FakeSession:
            def __init__(self, **kwargs):
                self.handlers = {}
                self.llm = kwargs["llm"]
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
                self.realtime_session = self.llm.session()
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
            realtime=types.SimpleNamespace(
                RealtimeModel=FakeModel,
                RealtimeSession=FakeRealtimeSession,
                events=types.SimpleNamespace(CallStartedEvent=FakeCallStartedEvent),
            )
        )
        livekit.rtc = types.SimpleNamespace(
            ParticipantKind=types.SimpleNamespace(
                PARTICIPANT_KIND_STANDARD=0,
                PARTICIPANT_KIND_SIP=3,
                PARTICIPANT_KIND_AGENT=4,
            ),
            TrackSource=types.SimpleNamespace(SOURCE_MICROPHONE=2),
        )
        livekit.agents = agents
        livekit.plugins = plugins
        ctx = FakeContext()

        async def send_event(event_type, **kwargs):
            events.append((event_type, kwargs))

        resolver = FakeCredentialResolver(ProviderCredential(provider="ultravox", api_key="tenant-a-key"))

        with patch.dict(
            sys.modules,
            {"livekit": livekit, "livekit.agents": agents, "livekit.plugins": plugins},
        ):
            task = asyncio.create_task(
                UltravoxLiveKitRuntime(settings(), resolver, None).run(ctx, spec(), send_event)
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertEqual(order, ["connect", "start"])
            self.assertEqual(resolver.calls, [("session-1", "ultravox")])
            self.assertEqual(sessions[0].llm.options["api_key"], "tenant-a-key")
            await asyncio.sleep(0)
            self.assertIn("voice.agent.ready", [event[0] for event in events])
            self.assertNotIn("voice.session.connected", [event[0] for event in events])

            call_started = FakeCallStartedEvent("ultravox-call-1")
            other_ultravox_event = object()
            realtime_sessions[0]._handle_ultravox_event(call_started)
            realtime_sessions[0]._handle_ultravox_event(call_started)
            realtime_sessions[0]._handle_ultravox_event(other_ultravox_event)
            await asyncio.sleep(0)
            provider_events = [event for event in events if event[0] == "voice.provider.session.started"]
            self.assertEqual(
                provider_events,
                [
                    (
                        "voice.provider.session.started",
                        {
                            "source": "ultravox",
                            "payload": {"provider_session_id": "ultravox-call-1"},
                        },
                    )
                ],
            )
            self.assertEqual(
                handled_ultravox_events,
                [call_started, call_started, other_ultravox_event],
            )

            internal = types.SimpleNamespace(identity="ingress-internal", kind=1)
            ctx.room.emit("participant_connected", internal)
            await asyncio.sleep(0)
            self.assertNotIn(
                "ingress-internal",
                [event[1].get("payload", {}).get("participant_identity") for event in events],
            )

            sip_participant = types.SimpleNamespace(identity="sip-session-1", kind=3)
            ctx.room.emit("participant_connected", sip_participant)
            await asyncio.sleep(0)
            self.assertIn(
                "sip-session-1",
                [event[1].get("payload", {}).get("participant_identity") for event in events],
            )

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
