"""Pure dashboard calculations: filter resolution, timezones and ratios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.analytics.domain.errors import InvalidDashboardFilterError
from app.modules.analytics.domain.statuses import NORMALIZED_CALL_STATUSES

UNASSIGNED_AGENT_LABEL = "Unassigned"
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class ResolvedFilters:
    from_datetime: datetime | None
    to_datetime: datetime | None
    agent_id: str | None
    status: str | None


def tenant_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def local_datetime(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def parse_filter_datetime(value: str | None, timezone: ZoneInfo, *, is_end: bool) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if "T" not in value and len(value) == 10:
            return datetime.combine(date.fromisoformat(value), time.max if is_end else time.min, tzinfo=timezone)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed
    except ValueError as exc:
        raise InvalidDashboardFilterError("from and to must be ISO dates or datetimes") from exc


def resolve_filters(
    *,
    from_value: str | None,
    to_value: str | None,
    agent_id: str | None,
    status: str | None,
    timezone: ZoneInfo,
) -> ResolvedFilters:
    if status and status not in NORMALIZED_CALL_STATUSES:
        raise InvalidDashboardFilterError(f"status must be one of: {', '.join(NORMALIZED_CALL_STATUSES)}")
    from_datetime = parse_filter_datetime(from_value, timezone, is_end=False)
    to_datetime = parse_filter_datetime(to_value, timezone, is_end=True)
    if from_datetime and to_datetime and from_datetime > to_datetime:
        raise InvalidDashboardFilterError("from must be earlier than or equal to to")
    return ResolvedFilters(from_datetime, to_datetime, agent_id, status)


def validate_page(page: int, page_size: int) -> None:
    if page < 1:
        raise InvalidDashboardFilterError("page must be greater than or equal to 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise InvalidDashboardFilterError("page_size must be between 1 and 100")


def percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return 0.0 if value is None else float(value)


def nullable_decimal_to_float(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)


def decimal_sum(values) -> float:
    return round(sum(decimal_to_float(value) for value in values), 2)
