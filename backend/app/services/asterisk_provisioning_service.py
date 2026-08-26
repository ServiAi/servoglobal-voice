from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantIntegrationEvent, TenantSipRoute
from app.schemas.asterisk_provisioning import (
    AsteriskApplyResult,
    AsteriskApplyResultsResponse,
    AsteriskDesiredRoute,
    AsteriskDesiredStateResponse,
)
from app.services.voice_sip_route_service import VoiceSipRouteService


class AsteriskProvisioningService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.route_service = VoiceSipRouteService(db)

    @staticmethod
    def route_key(route_id: str) -> str:
        compact = route_id.replace("-", "").lower()
        if len(compact) != 32 or any(char not in "0123456789abcdef" for char in compact):
            raise ValueError("invalid_route_id")
        return f"route-{compact}"

    def desired_state(self) -> AsteriskDesiredStateResponse:
        routes = list(self.db.scalars(select(TenantSipRoute).order_by(TenantSipRoute.id)))
        revision_source = [
            [route.id, route.desired_revision, route.status] for route in routes
        ]
        snapshot_revision = hashlib.sha256(
            json.dumps(revision_source, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return AsteriskDesiredStateResponse(
            snapshot_revision=snapshot_revision,
            routes=[
                AsteriskDesiredRoute(
                    route_id=route.id,
                    route_key=self.route_key(route.id),
                    desired_revision=route.desired_revision,
                    applied_revision=route.applied_revision,
                    enabled=route.status == "active",
                    sip_username=route.sip_username,
                    sip_password=(
                        self.route_service.decrypt_password(route)
                        if route.status == "active"
                        else None
                    ),
                    caller_id=route.caller_id,
                )
                for route in routes
            ],
        )

    def apply_results(
        self, results: list[AsteriskApplyResult]
    ) -> AsteriskApplyResultsResponse:
        accepted = 0
        ignored = 0
        now = datetime.now(timezone.utc)
        for result in results:
            route = self.db.get(TenantSipRoute, result.route_id)
            if route is None or route.desired_revision != result.revision:
                ignored += 1
                continue
            expected_status = "active" if route.status == "active" else "disabled"
            if result.success and (
                route.applied_revision == result.revision
                and route.provision_status == expected_status
            ):
                ignored += 1
                continue
            route.last_provision_attempt_at = now
            if result.success:
                route.applied_revision = result.revision
                route.provision_status = expected_status
                route.provision_error_code = None
                route.provisioned_at = now
            else:
                route.provision_status = "failed"
                route.provision_error_code = result.error_code or "apply_failed"
            self.db.add(
                TenantIntegrationEvent(
                    tenant_id=route.tenant_id,
                    provider="voice",
                    event_type="asterisk_route_provisioned" if result.success else "asterisk_route_failed",
                    status="success" if result.success else "failed",
                    resource_type="tenant_sip_route",
                    resource_id=route.id,
                    message=None,
                    metadata_json={"revision": result.revision},
                )
            )
            accepted += 1
        self.db.commit()
        return AsteriskApplyResultsResponse(accepted=accepted, ignored=ignored)
