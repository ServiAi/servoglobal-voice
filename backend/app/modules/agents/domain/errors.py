from __future__ import annotations


class AgentNotFoundError(ValueError):
    pass


class AgentConflictError(ValueError):
    pass


class AgentValidationError(ValueError):
    pass


class AgentCompilerError(ValueError):
    pass


class VoiceSelectionError(ValueError):
    pass
