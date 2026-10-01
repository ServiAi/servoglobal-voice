from __future__ import annotations


class VoiceSessionError(ValueError):
    pass


class VoiceSessionNotFoundError(VoiceSessionError):
    pass


class VoiceSessionsBusyError(VoiceSessionError):
    """A session of an agent being deleted cannot be released safely;
    ``code`` is the stable agent_delete_* reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SessionContextEnrichmentError(VoiceSessionError):
    """Base class for a failed controlled-enrichment attempt -- see
    VoiceSessionService.enrich_context(). Always fail-closed: the message
    is a stable code (session_context_*_conflict), never a generic string,
    so a caller can diagnose which identity actually conflicted."""


class SessionContextContactConflictError(SessionContextEnrichmentError):
    pass


class SessionContextLeadConflictError(SessionContextEnrichmentError):
    pass


class SessionContextTenantConflictError(SessionContextEnrichmentError):
    pass


class ContactResolutionError(ValueError):
    pass


class CrossTenantResolutionError(ContactResolutionError):
    """An explicit contact_id/lead_id does not belong to the given tenant,
    or a lead_id/contact_id pair points at two different contacts. Always
    a hard failure -- never silently degraded to "unresolved", since that
    could mask a real cross-tenant bug or an attempted ID-guessing attack."""


class InvalidRuntimeEventError(VoiceSessionError):
    """A runtime event that must be rejected as-is (HTTP 422)."""
