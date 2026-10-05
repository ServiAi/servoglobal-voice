"""Integration catalog rules (pure)."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_PROVIDERS = ("resend", "voice", "whatsapp", "calcom", "google_calendar", "chatwoot")


@dataclass(frozen=True)
class CatalogFacts:
    """What the catalog needs to know about one provider's configuration."""

    configured: bool
    provider_status: str | None
    has_error: bool


def catalog_status(*, configured: bool, provider_status: str | None, has_error: bool) -> str:
    if has_error or provider_status in {"error", "failed"}:
        return "error"
    if not configured:
        return "not_configured"
    if provider_status in {"active", "connected"}:
        return "active"
    return "configured"
