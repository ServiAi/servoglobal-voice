import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

from app.main import app
from app.services import calcom_service
from app.services.calcom_service import SlotUnavailableError, create_booking


class FakeAsyncClient:
    post_called = False

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "2026-06-24": [
                        {"start": "2026-06-24T10:00:00.000-05:00"},
                    ]
                },
            },
        )

    async def post(self, *args, **kwargs):
        FakeAsyncClient.post_called = True
        return httpx.Response(201, json={"status": "success"})


class CalcomAvailabilityHardeningTests(unittest.TestCase):
    def setUp(self):
        calcom_service.settings.CAL_API_KEY = "test-key"
        calcom_service.settings.CAL_EVENT_TYPE_ID = "123"
        calcom_service.settings.CAL_TIMEZONE = "America/Bogota"
        FakeAsyncClient.post_called = False

    def test_invalid_availability_input_returns_400_not_502(self):
        client = TestClient(app)
        response = client.post(
            "/api/v1/availability",
            json={"date": "la otra semana temprano", "jornada": "tarde"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Expresion temporal no soportada", response.json()["detail"])

    def test_create_booking_checks_slot_before_posting_to_calcom(self):
        with patch.object(calcom_service.httpx, "AsyncClient", FakeAsyncClient):
            with self.assertRaises(SlotUnavailableError):
                asyncio.run(
                    create_booking(
                        date_str="2026-06-24",
                        time_str="09:00",
                        name="Maria",
                        email="maria@example.com",
                        phone="+573001112233",
                    )
                )

        self.assertFalse(FakeAsyncClient.post_called)

    def test_booking_endpoint_returns_409_for_unavailable_slot(self):
        async_mock = AsyncMock(side_effect=SlotUnavailableError("Horario ocupado"))

        with patch("app.api.endpoints.calcom.create_booking", async_mock):
            client = TestClient(app)
            response = client.post(
                "/api/v1/bookings",
                json={
                    "date_str": "2026-06-24",
                    "time_str": "09:00",
                    "name": "Maria",
                    "email": "maria@example.com",
                    "phone": "+573001112233",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Horario ocupado")


if __name__ == "__main__":
    unittest.main()
