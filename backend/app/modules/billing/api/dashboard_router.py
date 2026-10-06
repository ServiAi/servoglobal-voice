from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.billing.public import BillingFacade
from app.modules.identity.api.deps import get_current_auth_context
from app.modules.identity.public import AuthContext
from app.schemas.billing import TenantSavingsComparisonResponse, TenantUsageResponse

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/usage", response_model=TenantUsageResponse)
def get_dashboard_usage(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> TenantUsageResponse:
    return BillingFacade(db).get_usage(context.tenant_id)


@router.get("/savings-comparison", response_model=TenantSavingsComparisonResponse)
def get_dashboard_savings_comparison(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> TenantSavingsComparisonResponse:
    return BillingFacade(db).get_savings_comparison(context.tenant_id)
