from __future__ import annotations

import re


def normalize_recipient(destination: str | None) -> str | None:
    if not destination:
        return None
    cleaned = re.sub(r"[\s\-().]", "", destination)
    if re.fullmatch(r"\d{10}", cleaned):
        return f"+57{cleaned}"
    return cleaned or None


def mask_recipient(destination: str) -> str:
    normalized = normalize_recipient(destination) or ""
    return f"***{normalized[-4:]}" if len(normalized) > 4 else "***"
