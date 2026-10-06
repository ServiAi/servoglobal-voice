from decimal import Decimal

STATUS_NORMAL = "normal"
STATUS_APPROACHING_LIMIT = "approaching_limit"
STATUS_LIMIT_REACHED = "limit_reached"
STATUS_OVER_LIMIT = "over_limit"
STATUS_SUSPENDED_USAGE_LIMIT = "suspended_usage_limit"
DEFAULT_ALERT_THRESHOLDS = (80, 90, 100)


def status_for_usage(usage_percent: Decimal) -> str:
    if usage_percent > Decimal("100"):
        return STATUS_OVER_LIMIT
    if usage_percent >= Decimal("100"):
        return STATUS_LIMIT_REACHED
    if usage_percent >= Decimal("80"):
        return STATUS_APPROACHING_LIMIT
    return STATUS_NORMAL


def cost(minutes_used: Decimal, price_per_minute_usd: Decimal) -> Decimal:
    return minutes_used * price_per_minute_usd


def reached_alert_thresholds(usage_percent: Decimal) -> tuple[int, ...]:
    return tuple(value for value in DEFAULT_ALERT_THRESHOLDS if usage_percent >= Decimal(value))
