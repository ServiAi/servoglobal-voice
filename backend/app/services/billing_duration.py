from __future__ import annotations

from decimal import Decimal
from typing import Any


def provider_duration_to_minutes(value: Any) -> Decimal | None:
    """A provider billed duration (``"75s"``, ``"2m"`` or bare seconds) as minutes, 2 decimals."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return (Decimal(str(value)) / Decimal("60")).quantize(Decimal("0.01"))
    if not isinstance(value, str):
        return None

    duration = value.strip().lower()
    try:
        if duration.endswith("s"):
            return (Decimal(duration[:-1]) / Decimal("60")).quantize(Decimal("0.01"))
        if duration.endswith("m"):
            return Decimal(duration[:-1]).quantize(Decimal("0.01"))
    except Exception:
        return None
    return None
