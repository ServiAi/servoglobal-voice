class PublicCallFailure(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code


class VoiceRuntimeUnavailable(Exception):
    """The canonical voice runtime cannot serve a launch. ``code`` is one of
    ``unavailable`` (agent/config/context not usable), ``terminal`` (the session is
    over) or ``dispatch_failed`` (the room could not be created)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
