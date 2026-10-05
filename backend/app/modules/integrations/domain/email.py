"""Email pure helpers."""

from __future__ import annotations

import re


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def sanitize_resend_error(value: str | None) -> str:
    if not value:
        return "Resend request failed."
    sanitized = re.sub(r"[\r\n]+", " ", value)
    sanitized = re.sub(r"\bre_[A-Za-z0-9_-]+", "[redacted-api-key]", sanitized)
    sanitized = re.sub(r"(?i)\bAuthorization\s*[:=]?\s*(?:Bearer\s+)?[A-Za-z0-9._~+/=-]+", "Authorization [redacted-token]", sanitized)
    sanitized = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted-token]", sanitized)
    sanitized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", sanitized)
    sanitized = re.sub(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)", "[redacted-phone]", sanitized)
    return sanitized[:300]
