from __future__ import annotations

import unittest
import inspect
from importlib.metadata import version

from serviglobal_voice_runtime.call_factory import (
    CallCreationFailed,
    CallCreationOutcomeUnknown,
    UltravoxAgentCallFactory,
)


class Response:
    def __init__(self, status: int, data: dict):
        self.status = status
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self):
        return self.data


class Session:
    def __init__(self, agent: dict, post_status: int = 201):
        self.agent = agent
        self.post_status = post_status
        self.get_count = 0
        self.posts: list[dict] = []

    def get(self, *_args, **_kwargs):
        self.get_count += 1
        return Response(200, self.agent)

    def post(self, *_args, **kwargs):
        self.posts.append(kwargs["json"])
        return Response(self.post_status, {"callId": "call-1", "joinUrl": "wss://join"})


def kwargs(**overrides):
    values = {
        "api_key": "tenant-key",
        "agent_id": "remote-1",
        "observed_revision_id": "revision-1",
        "session_id": "session-1",
        "local_agent_id": "agent-1",
        "context": {"lead_name": "Ana"},
        "overrides": {"max_duration": "300s"},
        "input_sample_rate": 16000,
        "output_sample_rate": 24000,
    }
    values.update(overrides)
    return values


class CallFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_bootstrap_seam_is_pinned_to_ultravox_1_7_1(self):
        from livekit.plugins.ultravox.realtime import RealtimeSession

        source = inspect.getsource(RealtimeSession._main_task)
        self.assertEqual(version("livekit-plugins-ultravox"), "1.7.1")
        self.assertIn("http_session.post", source)
        self.assertIn("http_session.ws_connect", source)
        self.assertIn('response_json.get("joinUrl")', source)

    async def test_revalidates_tools_before_every_call_and_never_retries_post(self):
        session = Session({"agentId": "remote-1", "publishedRevisionId": "revision-1"})
        factory = UltravoxAgentCallFactory(session)

        await factory.create(**kwargs())
        await factory.create(**kwargs(session_id="session-2"))

        self.assertEqual(session.get_count, 2)
        self.assertEqual(len(session.posts), 2)
        self.assertEqual(session.posts[0]["templateContext"], {"lead_name": "Ana"})
        self.assertEqual(set(session.posts[0]["metadata"]), {"voice_session_id", "agent_id"})

    async def test_unsupported_client_tool_blocks_before_post(self):
        session = Session({
            "agentId": "remote-1",
            "callTemplate": {"selectedTools": [{"toolName": "unsafe", "client": {}}]},
        })
        with self.assertRaisesRegex(CallCreationFailed, "unsupported_client_tools"):
            await UltravoxAgentCallFactory(session).create(**kwargs())
        self.assertEqual(session.posts, [])

    async def test_rejects_non_allowlisted_override(self):
        session = Session({"agentId": "remote-1"})
        with self.assertRaisesRegex(CallCreationFailed, "overrides_invalid"):
            await UltravoxAgentCallFactory(session).create(**kwargs(overrides={"system_prompt": "no"}))
        self.assertEqual(session.get_count, 0)

    async def test_5xx_is_outcome_unknown_and_post_is_not_retried(self):
        session = Session({"agentId": "remote-1"}, post_status=503)
        with self.assertRaisesRegex(CallCreationOutcomeUnknown, "outcome_unknown"):
            await UltravoxAgentCallFactory(session).create(**kwargs())
        self.assertEqual(len(session.posts), 1)


if __name__ == "__main__":
    unittest.main()
