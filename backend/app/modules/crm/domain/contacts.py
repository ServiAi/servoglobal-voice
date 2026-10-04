"""Pure contact rules."""

from __future__ import annotations

import re


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    # Remove all spaces, tabs, dashes, parenthesis, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)
    if not cleaned:
        return None
        
    # Colombia specific rule: if it has 10 digits and doesn't start with "+"
    # e.g., "3001112233" -> "+573001112233"
    if re.match(r"^\d{10}$", cleaned):
        cleaned = f"+57{cleaned}"
        
    return cleaned
