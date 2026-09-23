from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.tool_http_limits import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_PORTS,
    MAX_RESPONSE_BYTES,
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
)

# HTTPX's INFO message includes the complete URL, including mapped customer
# identifiers in path/query values. Higher-level services record sanitized
# status metadata, so suppress this lower-level request-line log.
logging.getLogger("httpx").setLevel(logging.WARNING)


class UnsafeUrlError(ValueError):
    """Raised for any URL/target that fails SSRF validation. `reason` is a
    stable, non-leaking code (never includes the raw URL/IP) safe to surface
    up to ToolExecutionError."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ResponseTooLargeError(RuntimeError):
    pass


class UpstreamRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedTarget:
    scheme: str
    hostname: str
    port: int
    resolved_ip: str
    path_and_query: str


@dataclass(frozen=True)
class SafeHttpResponse:
    status_code: int
    headers: dict[str, str]
    body_bytes: bytes
    content_type: str | None


def _is_unsafe_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    # Redundant with is_link_local on most platforms, kept explicit per the
    # cloud metadata endpoint being the single highest-value SSRF target.
    return ip_str == "169.254.169.254"


def validate_and_resolve(url: str, *, allow_http: bool) -> ResolvedTarget:
    """Parses and validates a tenant-supplied URL, then resolves its
    hostname to a concrete IP and validates THAT IP too -- resolving once
    here and pinning the same IP for the actual connection (see
    SafeHttpClient) is what closes the DNS-rebinding window: a naive
    "check the hostname string, then let the HTTP client resolve it again"
    approach would let a second lookup return a different (private) IP.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError("invalid_url") from exc
    if parsed.scheme == "http" and not allow_http:
        raise UnsafeUrlError("unsafe_scheme")
    if parsed.scheme not in ("https", "http"):
        raise UnsafeUrlError("unsafe_scheme")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("credentials_in_url")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("missing_hostname")

    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("port_not_allowed")

    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError("dns_resolution_failed") from exc
    if not addr_infos:
        raise UnsafeUrlError("dns_resolution_failed")

    resolved_ips = {info[4][0] for info in addr_infos}
    # Any bad IP rejects the whole request -- never "pick the first good
    # one", since an attacker-controlled DNS answer can interleave a public
    # and a private record for the same name.
    for ip_str in resolved_ips:
        if _is_unsafe_ip(ip_str):
            raise UnsafeUrlError("private_ip_target")

    resolved_ip = next(iter(resolved_ips))
    path_and_query = parsed.path or "/"
    if parsed.query:
        path_and_query = f"{path_and_query}?{parsed.query}"
    return ResolvedTarget(
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        resolved_ip=resolved_ip,
        path_and_query=path_and_query,
    )


class SafeHttpClient:
    """Makes exactly one safe outbound HTTP call: SSRF-validated target,
    connection pinned to the already-validated IP (TLS verification still
    checks the original hostname via the `sni_hostname` extension), no
    auto-redirects, bounded timeout, capped+streamed response, content-type
    allowlist. Has zero knowledge of tool config, mappings, or tenants --
    reusable as-is by a future MCP executor.

    `transport` exists only so tests can inject an httpx.MockTransport
    without making real socket connections; production code must never set
    it -- it bypasses the DNS resolution the connect step would otherwise
    always perform against the pinned URL.
    """

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        timeout_ms: int,
        allow_http: bool = False,
    ) -> SafeHttpResponse:
        timeout_ms = max(MIN_TIMEOUT_MS, min(timeout_ms, MAX_TIMEOUT_MS))
        target = validate_and_resolve(url, allow_http=allow_http)
        pinned_host = f"[{target.resolved_ip}]" if ":" in target.resolved_ip else target.resolved_ip
        pinned_url = f"{target.scheme}://{pinned_host}:{target.port}{target.path_and_query}"

        request_headers = dict(headers or {})
        request_headers["Host"] = target.hostname

        with httpx.Client(
            transport=self._transport,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_ms / 1000),
            verify=True,
        ) as client:
            request = client.build_request(
                method, pinned_url, headers=request_headers, params=params, json=json_body
            )
            request.extensions["sni_hostname"] = target.hostname
            try:
                response = client.send(request, stream=True)
            except httpx.HTTPError as exc:
                raise UpstreamRequestError(exc.__class__.__name__) from exc

            try:
                if response.is_redirect:
                    raise UnsafeUrlError("redirect_not_allowed")
                content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise UnsafeUrlError("content_type_not_allowed")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ResponseTooLargeError("response_too_large")
                return SafeHttpResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body_bytes=bytes(body),
                    content_type=content_type,
                )
            except httpx.HTTPError as exc:
                raise UpstreamRequestError(exc.__class__.__name__) from exc
            finally:
                response.close()
