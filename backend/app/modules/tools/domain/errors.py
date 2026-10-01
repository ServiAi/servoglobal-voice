from __future__ import annotations

from typing import Any

from app.modules.tools.domain.schema import (
    ToolSchemaError,
    validate_arguments_against_schema,
)


# Lives in the domain layer (not in the dispatcher) so the custom HTTP
# executor can raise them without importing the dispatcher back -- that
# lazy import used to be the only import cycle inside Tool Platform.
class ToolDispatchError(ValueError):
    pass


class ToolNotFoundError(ToolDispatchError):
    pass


class ToolNotAvailableError(ToolDispatchError):
    pass


class ToolArgumentError(ToolDispatchError):
    pass


class ToolExecutionError(ToolDispatchError):
    pass


def validate_tool_arguments(input_schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Shape check shared by the platform and custom paths; the actual
    validator lives in app.modules.tools.domain.schema."""
    try:
        validate_arguments_against_schema(input_schema, arguments)
    except ToolSchemaError as exc:
        raise ToolArgumentError(str(exc)) from exc
