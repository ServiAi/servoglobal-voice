"""SIP route invariants (pure): what a tenant's outbound route may contain."""

from __future__ import annotations

import re

from app.modules.telephony.domain.phone_numbers import SUPPORTED_OUTBOUND_COUNTRIES

HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
SIP_PASSWORD_FORBIDDEN = frozenset("\r\n;#[]")


def sip_username_for_route(route_id: str) -> str:
    compact = route_id.replace("-", "").lower()
    if len(compact) != 32 or any(
        char not in "0123456789abcdef" for char in compact
    ):
        raise ValueError("invalid_route_id")
    return f"route-{compact}"


def normalize_route_host(host: str) -> str:
    normalized = host.strip().lower()
    if not HOST_RE.fullmatch(normalized):
        raise ValueError("PBX host must be a hostname or IP address without protocol or port.")
    return normalized


def validate_sip_password(password: str | None) -> None:
    if password and (
        any(char in SIP_PASSWORD_FORBIDDEN for char in password)
        or not password.isascii()
        or not password.isprintable()
    ):
        raise ValueError("SIP password contains unsupported characters.")


def normalize_allowed_countries(allowed: list[str] | tuple[str, ...], default_country: str) -> list[str]:
    countries = sorted(set(allowed))
    if not countries or any(code not in SUPPORTED_OUTBOUND_COUNTRIES for code in countries):
        raise ValueError("At least one supported outbound country is required.")
    if default_country not in countries:
        raise ValueError("Default country must be enabled for the SIP route.")
    return countries
