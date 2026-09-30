"""Composition root of Tool Platform: binds its ports to other modules'
public facades. The only file in app.modules.tools allowed to know which
concrete module serves each port."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.crm.public import CrmFacade
from app.modules.integrations.public import WhatsAppFacade
from app.modules.scheduling.public import SchedulingFacade
from app.modules.tools.application.ports import ToolPorts
from app.modules.voice.public import VoiceSessionFacade


def default_tool_ports(db: Session) -> ToolPorts:
    return ToolPorts(
        scheduling=SchedulingFacade(db),
        crm=CrmFacade(db),
        messaging=WhatsAppFacade(db),
        sessions=VoiceSessionFacade(db),
    )
