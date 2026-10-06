"""ORM -> DTO mapping; the only place Analytics rows become public values."""

from __future__ import annotations

from app.modules.analytics.contracts import AnalyticsAgentView, CallEventView, CallView
from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent


def agent_view(agent: Agent) -> AnalyticsAgentView:
    return AnalyticsAgentView(
        id=agent.id,
        tenant_id=agent.tenant_id,
        external_provider=agent.external_provider,
        external_agent_id=agent.external_agent_id,
        name=agent.name,
        channel_type=agent.channel_type,
        status=agent.status,
    )


def call_view(call: Call) -> CallView:
    return CallView(
        id=call.id,
        tenant_id=call.tenant_id,
        external_call_id=call.external_call_id,
        external_provider=call.external_provider,
        agent_id=call.agent_id,
        provider_agent_id=call.provider_agent_id,
        provider_status=call.provider_status,
        normalized_status=call.normalized_status,
        started_at=call.started_at,
        joined_at=call.joined_at,
        ended_at=call.ended_at,
        duration_seconds=call.duration_seconds,
        billed_minutes=call.billed_minutes,
        summary=call.summary,
        short_summary=call.short_summary,
        recording_url=call.recording_url,
        direction=call.direction,
        channel=call.channel,
        customer_phone=call.customer_phone,
        last_synced_at=call.last_synced_at,
    )


def event_view(event: CallEvent) -> CallEventView:
    return CallEventView(
        id=event.id,
        call_id=event.call_id,
        tenant_id=event.tenant_id,
        event_type=event.event_type,
        provider_event_id=event.provider_event_id,
        dedup_key=event.dedup_key,
        received_at=event.received_at,
    )
