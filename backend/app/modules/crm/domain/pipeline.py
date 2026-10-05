"""Pure pipeline rules: default stages, terminal stages, automatic transitions
and valid lead statuses. No SQLAlchemy, FastAPI or other modules."""

from __future__ import annotations

VALID_LEAD_STATUSES = {"open", "won", "lost", "unqualified", "paused"}

DEFAULT_STAGES = [
    {"key": "new", "name": "Nuevo", "position": 1, "is_default": True, "is_terminal": False},
    {"key": "contacted", "name": "Contactado", "position": 2, "is_default": False, "is_terminal": False},
    {"key": "connected", "name": "Conectado", "position": 3, "is_default": False, "is_terminal": False},
    {"key": "qualified", "name": "Calificado", "position": 4, "is_default": False, "is_terminal": False},
    {"key": "scheduled", "name": "Agendado", "position": 5, "is_default": False, "is_terminal": False},
    {"key": "voicemail", "name": "Buzón de voz", "position": 6, "is_default": False, "is_terminal": False},
    {"key": "follow_up", "name": "En seguimiento", "position": 7, "is_default": False, "is_terminal": False},
    {"key": "not_interested", "name": "No interesado", "position": 8, "is_default": False, "is_terminal": True},
    {"key": "won", "name": "Ganado", "position": 9, "is_default": False, "is_terminal": True},
    {"key": "lost", "name": "Perdido", "position": 10, "is_default": False, "is_terminal": True},
]

DEFAULT_STAGE_KEYS = {stage["key"] for stage in DEFAULT_STAGES}

TERMINAL_STAGES = {"not_interested", "won", "lost"}
AUTOMATIC_TRANSITIONS = {
    "new": {"contacted", "connected", "qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "contacted": {"connected", "qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "connected": {"qualified", "scheduled", "voicemail", "follow_up", "not_interested"},
    "qualified": {"scheduled", "voicemail", "follow_up", "not_interested"},
    "voicemail": {"contacted", "connected", "qualified", "scheduled", "follow_up", "not_interested"},
    "follow_up": {"contacted", "connected", "qualified", "scheduled", "voicemail", "not_interested"},
    "scheduled": set(),
    "not_interested": set(),
    "won": set(),
    "lost": set(),
}
