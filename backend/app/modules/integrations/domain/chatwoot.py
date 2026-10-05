"""Chatwoot pure helpers and value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatwootClientConfig:
    base_url: str
    account_id: int
    api_token: str
    default_inbox_id: int | None = None


def sanitize_chatwoot_error(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.lstrip().lower()
    if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
        return "Chatwoot devolvio una pagina HTML en vez de una respuesta de API. Verifica base_url y account_id."
    text = re.sub(r"api_access_token[\"']?\s*[:=]\s*[\"']?[\w.\-]+", "api_access_token=[REDACTED]", value)
    text = re.sub(r"\+?\d[\d\s().-]{6,}\d", "[REDACTED_PHONE]", text)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[REDACTED_EMAIL]", text)
    return text[:500]
