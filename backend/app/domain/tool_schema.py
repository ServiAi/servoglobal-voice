from __future__ import annotations

from typing import Any


class ToolSchemaError(ValueError):
    pass


def validate_arguments_against_schema(input_schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Minimal, purpose-built shape check (string/object/array/int/number/
    bool/null properties, required list, enum) -- not a general JSON Schema
    validator, and deliberately so: this codebase never adds a jsonschema
    dependency for the small, hand-authored schemas Platform Tools declare.
    Shared by ToolDispatchService (re-validating a live tool call) and
    PlatformToolContractService (validating a tool's effective LLM schema
    against what the model actually sent).
    """
    if not isinstance(arguments, dict):
        raise ToolSchemaError("Arguments must be an object.")
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ToolSchemaError("Tool input schema is invalid.")
    for required_key in required:
        if required_key not in arguments:
            raise ToolSchemaError(f"Missing required argument '{required_key}'.")
    for key, value in arguments.items():
        spec = properties.get(key)
        if spec is None:
            raise ToolSchemaError(f"Unknown argument '{key}'.")
        expected = spec.get("type")
        matches = {
            "string": isinstance(value, str),
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, False)
        if not matches:
            raise ToolSchemaError(f"Argument '{key}' must be of type '{expected}'.")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolSchemaError(f"Argument '{key}' is not an allowed value.")
