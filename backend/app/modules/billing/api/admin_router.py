from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.modules.billing.api.deps import get_current_internal_db
from app.modules.billing.public import (
    BillingFacade,
    BillingPlanInput,
    BillingTenantNotFoundError,
)
from app.modules.identity.public import IdentityAdminFacade
from app.schemas.billing import TenantPlanRequest

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _json(value):
    return jsonable_encoder(value, custom_encoder={Decimal: float})


@router.get("/tenants/usage-summary", response_model=list[dict[str, Any]])
def list_tenants_usage_summary(db: Session = Depends(get_current_internal_db)) -> list[dict]:
    return _json(BillingFacade(db).list_usage_summary())


@router.get("/usage-alerts", response_model=list[dict[str, Any]])
def list_usage_alerts(db: Session = Depends(get_current_internal_db)) -> list[dict]:
    return _json(BillingFacade(db).list_usage_alerts())


@router.get("/tenants/{tenant_id}/usage", response_model=dict[str, Any])
def get_tenant_usage(tenant_id: str, db: Session = Depends(get_current_internal_db)) -> dict:
    try:
        usage = BillingFacade(db).get_usage(tenant_id)
        savings = BillingFacade(db).get_savings_comparison(tenant_id)
    except BillingTenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "usage": _json(usage),
        "savings_comparison": _json(savings),
        "alerts": _json(usage.alerts),
    }


@router.patch("/tenants/{tenant_id}/plan", response_model=dict[str, Any])
def update_tenant_plan(
    tenant_id: str,
    payload: TenantPlanRequest,
    db: Session = Depends(get_current_internal_db),
) -> dict:
    billing = BillingFacade(db)
    try:
        usage = billing.update_plan(
            tenant_id,
            BillingPlanInput(payload.plan_key, payload.included_minutes, payload.price_per_minute_usd),
        )
        IdentityAdminFacade(db).get_tenant(tenant_id)
        savings = billing.get_savings_comparison(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"usage": _json(usage), "savings_comparison": _json(savings)}
