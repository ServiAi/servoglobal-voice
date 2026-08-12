from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.services.turnstile_verification_service import TurnstileVerificationService


class _Response:
    def __init__(self, payload: dict, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail

    def raise_for_status(self) -> None:
        if self.fail:
            raise httpx.HTTPStatusError("failed", request=None, response=None)

    def json(self) -> dict:
        return self.payload


class _Client:
    response = _Response({"success": True})

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, *_args, **_kwargs):
        return self.response


class TurnstileVerificationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_or_secret_fails_closed(self) -> None:
        self.assertFalse(await TurnstileVerificationService(secret="").verify("token", "127.0.0.1"))
        self.assertFalse(await TurnstileVerificationService(secret="secret").verify("", "127.0.0.1"))

    async def test_only_explicit_success_is_accepted(self) -> None:
        with patch("app.services.turnstile_verification_service.httpx.AsyncClient", _Client):
            _Client.response = _Response({"success": True})
            self.assertTrue(await TurnstileVerificationService(secret="secret").verify("token", "127.0.0.1"))
            _Client.response = _Response({"success": False})
            self.assertFalse(await TurnstileVerificationService(secret="secret").verify("token", "127.0.0.1"))
    async def test_http_and_invalid_json_fail_closed(self) -> None:
        with patch("app.services.turnstile_verification_service.httpx.AsyncClient", _Client):
            _Client.response = _Response({}, fail=True)
            self.assertFalse(await TurnstileVerificationService(secret="secret").verify("token", "127.0.0.1"))
