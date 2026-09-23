from __future__ import annotations

import re

PLATFORM_NAMESPACES = frozenset({"calendar", "whatsapp", "crm", "handoff"})
CUSTOM_NAMESPACE = "custom"

_CUSTOM_KEY_RE = re.compile(r"^custom\.[a-z0-9_]{1,60}$")


class InvalidToolKeyError(ValueError):
    """Raised when a tenant-authored tool key violates the custom.* namespace rule."""


def validate_custom_key(key: str) -> None:
    """Reject any key that isn't `custom.<segment>` with a safe segment charset.

    This is the single source of truth for the namespace rule: platform tools
    own calendar.*/whatsapp.*/crm.*/handoff.*, tenants may only author
    custom.* keys. Called by TenantToolService before create/update; also
    mirrored by a DB CHECK constraint on tenant_tools.key as defense in depth.
    """
    if not key or not _CUSTOM_KEY_RE.match(key):
        raise InvalidToolKeyError(
            "Tool key must match 'custom.<segment>' with segment in [a-z0-9_]{1,60}."
        )
