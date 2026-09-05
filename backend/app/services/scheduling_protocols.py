from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

from app.models.crm import CrmBooking, CrmLead
from app.schemas.crm import BookingCreateRequest


@dataclass(frozen=True)
class SchedulingProviderCapabilities:
    schedules: bool = True
    native_schedules: bool = False
    event_types: bool = True
    native_event_types: bool = False
    resources: bool = True
    teams: bool = True
    native_round_robin: bool = False
    exceptions: bool = True
    native_exceptions: bool = False
    external_calendars: bool = True
    booking: bool = True
    reschedule: bool = True
    cancel: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


class SchedulingProvider(Protocol):
    """Runtime provider protocol for live bookings, slots, cancel, and reschedule."""

    def get_available_slots(
        self,
        *,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
        resource_id: str | None = None,
        team_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]: ...

    def create_booking(
        self,
        *,
        booking: CrmBooking,
        lead: CrmLead,
        body: BookingCreateRequest,
        payload: dict[str, Any] | None = None,
    ) -> CrmBooking: ...

    def cancel_booking(self, *, booking: CrmBooking) -> dict[str, Any]: ...

    def reschedule_booking(self, *, booking: CrmBooking, new_start_at: datetime) -> dict[str, Any]: ...


class SchedulingAdminProvider(Protocol):
    """Admin provider protocol for configuration, discovery, schedules, event types, and teams."""

    def capabilities(self) -> SchedulingProviderCapabilities: ...

    def discover(self) -> dict[str, Any]: ...

    def list_schedules(self) -> list[dict[str, Any]]: ...

    def get_schedule(self, schedule_id: str) -> dict[str, Any]: ...

    def create_schedule(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def update_schedule(self, schedule_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def delete_schedule(self, schedule_id: str) -> bool: ...

    def list_event_types(self) -> list[dict[str, Any]]: ...

    def get_event_type(self, event_type_id: str) -> dict[str, Any]: ...

    def create_event_type(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def update_event_type(self, event_type_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def delete_event_type(self, event_type_id: str) -> bool: ...

    def list_resources(self) -> list[dict[str, Any]]: ...

    def list_teams(self) -> list[dict[str, Any]]: ...

    def get_team(self, team_id: str) -> dict[str, Any]: ...

    def list_team_members(self, team_id: str) -> list[dict[str, Any]]: ...

    def sync(self) -> dict[str, Any]: ...
