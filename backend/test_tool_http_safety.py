from __future__ import annotations

import logging
import socket
import unittest
from unittest.mock import patch

import httpx

from app.services.tool_http_safety import (
    ResponseTooLargeError,
    SafeHttpClient,
    UnsafeUrlError,
    UpstreamRequestError,
    validate_and_resolve,
)


def _addrinfo(ips: list[str]) -> list[tuple]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


class ValidateAndResolveTests(unittest.TestCase):
    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_public_ip_is_allowed(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])
        target = validate_and_resolve("https://example.test/path", allow_http=False)
        self.assertEqual(target.resolved_ip, "93.184.216.34")

    def test_http_scheme_rejected_by_default(self):
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("http://example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "unsafe_scheme")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_http_scheme_allowed_when_explicitly_enabled(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])
        target = validate_and_resolve("http://example.test/path", allow_http=True)
        self.assertEqual(target.scheme, "http")

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://user:pass@example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "credentials_in_url")

    def test_disallowed_port_rejected(self):
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://example.test:8080/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "port_not_allowed")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_loopback_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["127.0.0.1"])
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://localhost/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_ipv6_loopback_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))]
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_link_local_ipv6_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443, 0, 0))]
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_cloud_metadata_ip_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["169.254.169.254"])
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_rfc1918_ranges_rejected(self, mock_getaddrinfo):
        for ip in ("10.0.0.5", "172.16.0.1", "192.168.1.1"):
            with self.subTest(ip=ip):
                mock_getaddrinfo.return_value = _addrinfo([ip])
                with self.assertRaises(UnsafeUrlError) as ctx:
                    validate_and_resolve("https://example.test/path", allow_http=False)
                self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_mixed_public_and_private_dns_answers_reject_whole_request(self, mock_getaddrinfo):
        """DNS-rebinding defense: any unsafe IP in the answer set blocks the
        request entirely -- never 'pick the first good one'."""
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34", "10.0.0.5"])
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://example.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "private_ip_target")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_dns_resolution_failure_is_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("no such host")
        with self.assertRaises(UnsafeUrlError) as ctx:
            validate_and_resolve("https://does-not-resolve.test/path", allow_http=False)
        self.assertEqual(ctx.exception.reason, "dns_resolution_failed")


class SafeHttpClientTests(unittest.TestCase):
    def _client_for(self, handler) -> SafeHttpClient:
        transport = httpx.MockTransport(handler)
        return SafeHttpClient(transport=transport)

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_successful_json_response_round_trips(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["host"], "example.test")
            return httpx.Response(200, json={"balance": 4500}, headers={"content-type": "application/json"})

        client = self._client_for(handler)
        response = client.request(method="GET", url="https://example.test/balance", timeout_ms=5000)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body_bytes, b'{"balance":4500}')

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_follow_redirects_is_disabled(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://example.test/other"})

        client = self._client_for(handler)
        with self.assertRaises(UnsafeUrlError) as ctx:
            client.request(method="GET", url="https://example.test/balance", timeout_ms=5000)
        self.assertEqual(ctx.exception.reason, "redirect_not_allowed")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_disallowed_content_type_is_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, html="<html></html>", headers={"content-type": "text/html"})

        client = self._client_for(handler)
        with self.assertRaises(UnsafeUrlError) as ctx:
            client.request(method="GET", url="https://example.test/balance", timeout_ms=5000)
        self.assertEqual(ctx.exception.reason, "content_type_not_allowed")

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_oversized_response_is_aborted(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])
        oversized = b"x" * (1_048_576 + 1)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=oversized, headers={"content-type": "text/plain"})

        client = self._client_for(handler)
        with self.assertRaises(ResponseTooLargeError):
            client.request(method="GET", url="https://example.test/balance", timeout_ms=5000)

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_timeout_above_ceiling_is_clamped(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])
        captured_timeouts = []

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={}, headers={"content-type": "application/json"})

        transport = httpx.MockTransport(handler)
        client = SafeHttpClient(transport=transport)
        with patch("app.services.tool_http_safety.httpx.Client", wraps=httpx.Client) as spy:
            client.request(method="GET", url="https://example.test/x", timeout_ms=999_999)
            _, kwargs = spy.call_args
            timeout: httpx.Timeout = kwargs["timeout"]
            self.assertEqual(timeout.connect, 15.0)

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_private_target_is_rejected_before_any_transport_call(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["127.0.0.1"])

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("transport should never be invoked for an unsafe target")

        client = self._client_for(handler)
        with self.assertRaises(UnsafeUrlError):
            client.request(method="GET", url="https://example.test/balance", timeout_ms=5000)

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_public_ipv6_target_is_bracketed(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0))
        ]
        client = self._client_for(
            lambda request: httpx.Response(200, json={}, headers={"content-type": "application/json"})
        )
        response = client.request(method="GET", url="https://example.test/x", timeout_ms=5000)
        self.assertEqual(response.status_code, 200)

    @patch("app.services.tool_http_safety.socket.getaddrinfo")
    def test_stream_read_timeout_is_sanitized(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo(["93.184.216.34"])

        class BrokenStream(httpx.SyncByteStream):
            def __iter__(self):
                yield b"{"
                raise httpx.ReadTimeout("synthetic timeout")

        client = self._client_for(
            lambda request: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=BrokenStream()
            )
        )
        with self.assertRaises(UpstreamRequestError):
            client.request(method="GET", url="https://example.test/x", timeout_ms=5000)

    def test_httpx_request_urls_are_not_logged_at_info(self):
        self.assertGreaterEqual(logging.getLogger("httpx").getEffectiveLevel(), logging.WARNING)


if __name__ == "__main__":
    unittest.main()
