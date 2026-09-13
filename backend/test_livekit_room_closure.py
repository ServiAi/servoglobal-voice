import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.livekit_runtime_backend import LiveKitRuntimeBackend


class LiveKitRoomClosureTests(unittest.TestCase):
    def test_closes_only_the_session_room_and_confirms_absence(self) -> None:
        room = MagicMock()
        room.list_rooms = AsyncMock(side_effect=[
            SimpleNamespace(rooms=[SimpleNamespace(name="sg-vs-session-a")]),
            SimpleNamespace(rooms=[]),
        ])
        room.delete_room = AsyncMock()
        client = MagicMock()
        client.room = room
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("app.services.livekit_runtime_backend.settings") as settings, patch("livekit.api.LiveKitAPI", return_value=client):
            settings.LIVEKIT_URL = "wss://livekit.example"
            settings.LIVEKIT_API_KEY = "test-key"
            settings.LIVEKIT_API_SECRET = "test-secret"
            asyncio.run(LiveKitRuntimeBackend().close_session_room("session-a"))
        self.assertEqual(room.delete_room.await_args.args[0].room, "sg-vs-session-a")
        self.assertEqual(room.list_rooms.await_count, 2)
        self.assertEqual(room.list_rooms.await_args_list[0].args[0].names, ["sg-vs-session-a"])

    def test_does_not_claim_success_when_room_remains(self) -> None:
        room = MagicMock()
        room.list_rooms = AsyncMock(side_effect=[
            SimpleNamespace(rooms=[SimpleNamespace(name="sg-vs-session-a")]),
            SimpleNamespace(rooms=[SimpleNamespace(name="sg-vs-session-a")]),
        ])
        room.delete_room = AsyncMock()
        client = MagicMock()
        client.room = room
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("app.services.livekit_runtime_backend.settings") as settings, patch("livekit.api.LiveKitAPI", return_value=client):
            settings.LIVEKIT_URL = "wss://livekit.example"
            settings.LIVEKIT_API_KEY = "test-key"
            settings.LIVEKIT_API_SECRET = "test-secret"
            with self.assertRaisesRegex(RuntimeError, "could not be confirmed"):
                asyncio.run(LiveKitRuntimeBackend().close_session_room("session-a"))

    def test_concurrent_room_teardown_is_idempotent(self) -> None:
        room = MagicMock()
        room.list_rooms = AsyncMock(side_effect=[
            SimpleNamespace(rooms=[SimpleNamespace(name="sg-vs-session-a")]),
            SimpleNamespace(rooms=[]),
            SimpleNamespace(rooms=[]),
        ])
        room.delete_room = AsyncMock(side_effect=RuntimeError("room already gone"))
        client = MagicMock()
        client.room = room
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        with patch("app.services.livekit_runtime_backend.settings") as settings, patch("livekit.api.LiveKitAPI", return_value=client):
            settings.LIVEKIT_URL = "wss://livekit.example"
            settings.LIVEKIT_API_KEY = "test-key"
            settings.LIVEKIT_API_SECRET = "test-secret"
            asyncio.run(LiveKitRuntimeBackend().close_session_room("session-a"))
