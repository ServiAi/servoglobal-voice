from __future__ import annotations

# Cal.com API v2 explicit version headers per resource family
# Note: API v1 is permanently retired.
CALCOM_API_VERSIONS: dict[str, str] = {
    "bookings": "2024-08-13",
    "slots": "2024-09-04",
    "schedules": "2024-06-11",
    "event_types": "2024-06-14",
    "teams": "2024-08-13",
    "memberships": "2024-08-13",
    "users": "2024-08-13",
    "me": "2024-08-13",
}

DEFAULT_CALCOM_API_VERSION = "2024-08-13"
