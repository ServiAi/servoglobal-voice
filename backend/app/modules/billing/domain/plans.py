from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.modules.billing.domain.errors import InvalidBillingPlanError

PLAN_WEB_CONVERSION = "web_conversion"
PLAN_VOICE_CLOUD_PBX = "voice_cloud_pbx"
PLAN_ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class PlanDefinition:
    key: str
    name: str
    included_minutes: Decimal
    price_per_minute_usd: Decimal


PLAN_DEFINITIONS = {
    PLAN_WEB_CONVERSION: PlanDefinition(
        PLAN_WEB_CONVERSION, "Plan Web Conversion", Decimal("2000.00"), Decimal("0.1600")
    ),
    PLAN_VOICE_CLOUD_PBX: PlanDefinition(
        PLAN_VOICE_CLOUD_PBX, "Plan Voice Cloud / PBX", Decimal("2000.00"), Decimal("0.1800")
    ),
}


def decimal(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal("0") if value is None else value if isinstance(value, Decimal) else Decimal(str(value))


def quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def normalize_plan(
    plan_key: str,
    included_minutes: Decimal | None = None,
    price_per_minute_usd: Decimal | None = None,
) -> tuple[str, Decimal, Decimal]:
    if plan_key in PLAN_DEFINITIONS:
        plan = PLAN_DEFINITIONS[plan_key]
        return plan.name, plan.included_minutes, plan.price_per_minute_usd
    if plan_key != PLAN_ENTERPRISE:
        raise InvalidBillingPlanError(f"Unknown plan_key '{plan_key}'")
    minutes, price = decimal(included_minutes), decimal(price_per_minute_usd)
    if minutes < Decimal("2000"):
        raise InvalidBillingPlanError("Enterprise included_minutes must be greater than or equal to 2000")
    if not Decimal("0.14") <= price <= Decimal("0.15"):
        raise InvalidBillingPlanError("Enterprise price_per_minute_usd must be between 0.14 and 0.15")
    return "Enterprise", quantize(minutes, "0.01"), quantize(price, "0.0001")
