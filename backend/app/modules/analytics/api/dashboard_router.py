"""HTTP surface of the call dashboard (``/api/v1/dashboard`` except the Billing routes)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.analytics.contracts import DashboardFilters
from app.modules.analytics.domain.errors import InvalidDashboardFilterError
from app.modules.analytics.public import AnalyticsDashboard
from app.modules.identity.api.deps import get_current_auth_context
from app.modules.identity.public import AuthContext
from app.schemas.dashboard import (
    DashboardAgentDistributionResponse,
    DashboardHeatmapResponse,
    DashboardKpisResponse,
    DashboardRecentCallsResponse,
    DashboardStatusDistributionResponse,
    DashboardTrendsResponse,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


def _filters(
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> DashboardFilters:
    return DashboardFilters(from_value=from_value, to_value=to_value, agent_id=agent_id, status=status)


def _unprocessable(exc: InvalidDashboardFilterError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/kpis", response_model=DashboardKpisResponse)
def get_dashboard_kpis(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardKpisResponse:
    try:
        view = AnalyticsDashboard(db).kpis(context.tenant.id, context.tenant.timezone, filters)
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardKpisResponse(**asdict(view))


@router.get("/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardTrendsResponse:
    try:
        view = AnalyticsDashboard(db).trends(context.tenant.id, context.tenant.timezone, filters)
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardTrendsResponse.model_validate(asdict(view))


@router.get("/status-distribution", response_model=DashboardStatusDistributionResponse)
def get_dashboard_status_distribution(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardStatusDistributionResponse:
    try:
        view = AnalyticsDashboard(db).status_distribution(context.tenant.id, context.tenant.timezone, filters)
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardStatusDistributionResponse.model_validate(asdict(view))


@router.get("/agent-distribution", response_model=DashboardAgentDistributionResponse)
def get_dashboard_agent_distribution(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardAgentDistributionResponse:
    try:
        view = AnalyticsDashboard(db).agent_distribution(context.tenant.id, context.tenant.timezone, filters)
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardAgentDistributionResponse.model_validate(asdict(view))


@router.get("/heatmap", response_model=DashboardHeatmapResponse)
def get_dashboard_heatmap(
    filters: DashboardFilters = Depends(_filters),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardHeatmapResponse:
    try:
        view = AnalyticsDashboard(db).heatmap(context.tenant.id, context.tenant.timezone, filters)
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardHeatmapResponse.model_validate(asdict(view))


@router.get("/recent-calls", response_model=DashboardRecentCallsResponse)
def get_dashboard_recent_calls(
    filters: DashboardFilters = Depends(_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> DashboardRecentCallsResponse:
    try:
        view = AnalyticsDashboard(db).recent_calls(
            context.tenant.id, context.tenant.timezone, filters, page=page, page_size=page_size
        )
    except InvalidDashboardFilterError as exc:
        raise _unprocessable(exc) from exc
    return DashboardRecentCallsResponse.model_validate(asdict(view))
