from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.schemas.billing import TenantSavingsComparisonResponse, TenantUsageResponse
from app.schemas.dashboard import (
    DashboardAgentDistributionResponse,
    DashboardHeatmapResponse,
    DashboardKpisResponse,
    DashboardRecentCallsResponse,
    DashboardStatusDistributionResponse,
    DashboardTrendsResponse,
)
from app.services.dashboard_analytics_service import DashboardAnalyticsService, DashboardFilters
from app.services.tenant_usage_service import TenantUsageService

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


def _filters(
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> DashboardFilters:
    return DashboardFilters(
        from_value=from_value,
        to_value=to_value,
        agent_id=agent_id,
        status=status,
    )


@router.get("/kpis", response_model=DashboardKpisResponse)
def get_dashboard_kpis(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardKpisResponse:
    return DashboardAnalyticsService(db).get_kpis(context.tenant, filters)


@router.get("/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardTrendsResponse:
    return DashboardAnalyticsService(db).get_trends(context.tenant, filters)


@router.get("/status-distribution", response_model=DashboardStatusDistributionResponse)
def get_dashboard_status_distribution(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardStatusDistributionResponse:
    return DashboardAnalyticsService(db).get_status_distribution(context.tenant, filters)


@router.get("/agent-distribution", response_model=DashboardAgentDistributionResponse)
def get_dashboard_agent_distribution(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardAgentDistributionResponse:
    return DashboardAnalyticsService(db).get_agent_distribution(context.tenant, filters)


@router.get("/heatmap", response_model=DashboardHeatmapResponse)
def get_dashboard_heatmap(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardHeatmapResponse:
    return DashboardAnalyticsService(db).get_heatmap(context.tenant, filters)


@router.get("/recent-calls", response_model=DashboardRecentCallsResponse)
def get_dashboard_recent_calls(
    filters: DashboardFilters = Depends(_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardRecentCallsResponse:
    return DashboardAnalyticsService(db).get_recent_calls(
        context.tenant,
        filters,
        page=page,
        page_size=page_size,
    )


@router.get("/usage", response_model=TenantUsageResponse)
def get_dashboard_usage(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> TenantUsageResponse:
    return TenantUsageService(db).get_usage(context.tenant)


@router.get("/savings-comparison", response_model=TenantSavingsComparisonResponse)
def get_dashboard_savings_comparison(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> TenantSavingsComparisonResponse:
    return TenantUsageService(db).get_savings_comparison(context.tenant)
