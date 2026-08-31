from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import whatsapp_client
from app.services.meta_client import MetaClient
from app.services.whatsapp_client import WhatsAppClientConfig, WhatsAppCloudClient


class _Response:
    status_code = 200

    def json(self):
        return {}


class _RecordingClient:
    requested_url: str | None = None
    request_kwargs: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def request(self, method, url, **kwargs):
        _RecordingClient.requested_url = url
        _RecordingClient.request_kwargs = kwargs
        return _Response()


class WhatsAppGraphVersionTests(unittest.TestCase):
    def test_whatsapp_client_version_is_not_the_expired_hardcode(self):
        self.assertNotEqual(whatsapp_client.WHATSAPP_GRAPH_VERSION, "v19.0")

    def test_whatsapp_client_version_comes_from_settings(self):
        self.assertEqual(whatsapp_client.WHATSAPP_GRAPH_VERSION, settings.WHATSAPP_GRAPH_VERSION)

    def test_request_builds_url_with_configured_version(self):
        _RecordingClient.requested_url = None
        with patch("app.services.whatsapp_client.httpx.Client", _RecordingClient):
            WhatsAppCloudClient()._request(
                "GET", "phone-id", WhatsAppClientConfig(access_token="tok", phone_number_id="phone-id")
            )
        self.assertEqual(
            _RecordingClient.requested_url,
            f"https://graph.facebook.com/{whatsapp_client.WHATSAPP_GRAPH_VERSION}/phone-id",
        )

    def test_meta_client_base_url_uses_configured_version(self):
        with patch.object(settings, "WHATSAPP_GRAPH_VERSION", "v99.0"), \
             patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", "phone-id"):
            client = MetaClient()
        self.assertEqual(client._base_url, "https://graph.facebook.com/v99.0/phone-id/messages")

    def test_flow_asset_upload_uses_multipart_without_manual_content_type(self):
        with patch("app.services.whatsapp_client.httpx.Client", _RecordingClient):
            WhatsAppCloudClient().upload_flow_json(
                WhatsAppClientConfig(access_token="tok", phone_number_id="phone-id"),
                flow_id="flow-1",
                flow_json={"version": "7.3", "screens": []},
            )
        kwargs = _RecordingClient.request_kwargs or {}
        self.assertIn("files", kwargs)
        self.assertEqual(kwargs["files"]["file"][0], "flow.json")
        self.assertEqual(kwargs["files"]["file"][2], "application/json")
        self.assertNotIn("Content-Type", kwargs["headers"])

    def test_flow_creation_uses_multipart_fields(self):
        with patch("app.services.whatsapp_client.httpx.Client", _RecordingClient):
            WhatsAppCloudClient().create_flow(
                WhatsAppClientConfig(access_token="tok", phone_number_id="phone-id"),
                waba_id="waba-1",
                name="Lead Flow",
                categories=["LEAD_GENERATION"],
                clone_flow_id="flow-parent",
            )
        kwargs = _RecordingClient.request_kwargs or {}
        self.assertEqual(kwargs["files"]["name"], (None, "Lead Flow"))
        self.assertEqual(kwargs["files"]["clone_flow_id"], (None, "flow-parent"))
        self.assertNotIn("Content-Type", kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
