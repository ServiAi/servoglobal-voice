from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")

# Documents the only roots a request-side mapping source path may start
# with. Enforcement itself is structural (see build_request_values): the
# roots dict passed to resolve_path only ever contains these three keys, so
# any other root segment fails as a plain "missing key" lookup -- there is
# no separate allowlist branch to keep in sync.
ALLOWED_REQUEST_ROOTS = frozenset({"args", "context", "binding"})

_MAX_PATH_DEPTH = 8


class MappingPathError(ValueError):
    pass


def resolve_path(root: dict[str, Any], path: str, *, allow_list_index: bool) -> Any:
    """Walks a dotted path of plain dict-key lookups (and, only when
    `allow_list_index` is true, numeric list indices) against `root`. No
    eval/exec/getattr/attribute-access, no wildcards, no slicing -- a
    segment that isn't a literal dict key (or list index, when allowed) is
    rejected, never silently skipped.
    """
    segments = path.split(".")
    if not segments or not all(segments):
        raise MappingPathError(f"Invalid path '{path}'.")
    if len(segments) > _MAX_PATH_DEPTH:
        raise MappingPathError(f"Path '{path}' exceeds the maximum depth of {_MAX_PATH_DEPTH}.")

    current: Any = root
    for segment in segments:
        if isinstance(current, dict):
            if segment not in current:
                raise MappingPathError(f"Missing key '{segment}' in path '{path}'.")
            current = current[segment]
        elif isinstance(current, list):
            if not allow_list_index or not segment.isdigit():
                raise MappingPathError(f"List index not permitted at '{segment}' in path '{path}'.")
            index = int(segment)
            if index >= len(current):
                raise MappingPathError(f"Index {index} out of range in path '{path}'.")
            current = current[index]
        else:
            raise MappingPathError(f"Cannot resolve '{segment}' in path '{path}'.")
    return current


def build_request_values(
    mapping: dict[str, str], *, args: dict[str, Any], context: dict[str, Any], binding_config: dict[str, Any]
) -> dict[str, Any]:
    """Resolves a query/body/path mapping dict into concrete values. Never
    allows list indexing on the request side (`allow_list_index=False`) --
    args/context/binding are all plain objects a tenant declares fields
    against, not arrays.
    """
    roots = {"args": args, "context": context, "binding": {"config": binding_config}}
    values: dict[str, Any] = {}
    for target_field, source_path in mapping.items():
        values[target_field] = resolve_path(roots, source_path, allow_list_index=False)
    return values


def build_path(
    path_template: str,
    mapping: dict[str, str],
    *,
    args: dict[str, Any],
    context: dict[str, Any],
    binding_config: dict[str, Any],
) -> str:
    """Substitutes every `{name}` placeholder in `path_template` with its
    mapped value, URL-encoding each value (including any literal '/') so a
    resolved value can only ever fill in as an opaque path segment -- never
    inject additional path structure, a different host, or a scheme.
    """
    resolved = build_request_values(mapping, args=args, context=context, binding_config=binding_config)
    placeholders = set(_PLACEHOLDER_RE.findall(path_template))
    missing = placeholders - resolved.keys()
    if missing:
        raise MappingPathError(f"Unresolved path placeholder(s): {sorted(missing)}.")

    def _substitute(match: re.Match[str]) -> str:
        return quote(str(resolved[match.group(1)]), safe="")

    return _PLACEHOLDER_RE.sub(_substitute, path_template)


def extract_response_values(mapping: dict[str, str], response_json: Any) -> dict[str, Any]:
    """Resolves a response_mapping dict against the external API's JSON
    response, rooted at `response`. Numeric list indices ARE permitted here
    (unlike the request side) since real REST APIs commonly return
    {"results": [...]}; wildcards/slicing remain rejected because they
    aren't literal path segments this walker understands.
    """
    roots = {"response": response_json}
    values: dict[str, Any] = {}
    for output_field, response_path in mapping.items():
        values[output_field] = resolve_path(roots, response_path, allow_list_index=True)
    return values
