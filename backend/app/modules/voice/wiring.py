"""Composition root of Voice Orchestration: binds its ports to other
modules' public APIs. The only file in app.modules.voice allowed to know
which concrete module serves each port."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.analytics.public import VoiceCallProjectionFacade
from app.modules.crm.public import CrmFacade
from app.modules.voice.application.ports import CrmContextPort, VoiceProjectionPort


def crm_context(db: Session) -> CrmContextPort:
    return CrmFacade(db)


def voice_projection(db: Session) -> VoiceProjectionPort:
    return VoiceCallProjectionFacade(db)
