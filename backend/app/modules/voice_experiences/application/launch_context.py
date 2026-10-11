"""The runtime context a public launch (WebRTC or callback) may hand to the agent.

One policy for every public channel: business variables come only from the persisted submission,
only from fields collected BEFORE the call, and are then validated against SessionContextV1 by
the caller (voice.public) before anything is consumed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.voice_experiences.domain.limits import PUBLIC_CONTEXT_COLLECTION_MODES
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextField
from app.modules.voice_experiences.infrastructure.experience_models import TenantVoiceExperienceVersion
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
)


def trusted_variables(
    db: Session, version: TenantVoiceExperienceVersion, submission: TenantVoiceExperienceSubmission
) -> dict[str, object]:
    """``internal_only`` and ``collect_during_call`` values never reach the agent. The locale is
    session metadata (AgentVersion.language / ExperienceVersion.default_locale), not a variable: it
    must not spend one of SessionContextV1's 20 slots."""
    public_keys = {
        key
        for (key,) in db.execute(
            select(TenantVoiceContextField.key).where(
                TenantVoiceContextField.schema_id == version.context_schema_id,
                TenantVoiceContextField.collection_mode.in_(sorted(PUBLIC_CONTEXT_COLLECTION_MODES)),
            )
        ).all()
    }
    rows = db.scalars(
        select(TenantVoiceExperienceSubmissionValue).where(
            TenantVoiceExperienceSubmissionValue.submission_id == submission.id
        )
    ).all()
    return {row.field_key: row.value_json for row in rows if row.field_key in public_keys}
