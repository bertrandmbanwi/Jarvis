#!/usr/bin/env python3
"""Validate tool schemas, registry coverage, and permission coverage."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.agent import coordinator, tool_selector  # noqa: E402
from jarvis.agent.tools_schema import TOOL_REGISTRY, TOOL_SCHEMAS  # noqa: E402
from jarvis.core import cache, hardening  # noqa: E402
from jarvis.core.permissions import TOOL_PERMISSIONS, get_tool_permission  # noqa: E402


def _has_var_kwargs(fn: Any) -> bool:
    signature = inspect.signature(fn)
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())


def _required_args_match_signature(tool_name: str, fn: Any, schema: dict[str, Any]) -> list[str]:
    signature = inspect.signature(fn)
    if _has_var_kwargs(fn):
        return []
    parameters = signature.parameters
    missing = []
    for arg in schema.get("input_schema", {}).get("required", []):
        if arg not in parameters:
            missing.append(f"{tool_name}: required arg '{arg}' missing from {fn.__module__}.{fn.__name__}")
    return missing


def validate_tool_contracts() -> list[str]:
    """Return contract errors. Empty means the catalog is internally coherent."""
    errors: list[str] = []
    schema_names = []
    for index, schema in enumerate(TOOL_SCHEMAS):
        name = schema.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"schema[{index}] missing non-empty name")
            continue
        schema_names.append(name)
        input_schema = schema.get("input_schema")
        if not isinstance(input_schema, dict):
            errors.append(f"{name}: input_schema must be an object")
            continue
        if input_schema.get("type") != "object":
            errors.append(f"{name}: input_schema.type must be object")
        if not isinstance(input_schema.get("properties", {}), dict):
            errors.append(f"{name}: input_schema.properties must be an object")
        if not isinstance(input_schema.get("required", []), list):
            errors.append(f"{name}: input_schema.required must be a list when present")
        if name not in TOOL_REGISTRY:
            errors.append(f"{name}: schema has no registry entry")
            continue
        errors.extend(_required_args_match_signature(name, TOOL_REGISTRY[name], schema))
        permission = get_tool_permission(name)
        if not permission.capabilities:
            errors.append(f"{name}: permission has no capabilities")

    duplicate_names = sorted({name for name in schema_names if schema_names.count(name) > 1})
    for name in duplicate_names:
        errors.append(f"{name}: duplicate schema name")

    for name in sorted(set(TOOL_REGISTRY) - set(schema_names)):
        errors.append(f"{name}: registry entry has no schema")

    missing_explicit_permissions = sorted(set(TOOL_REGISTRY) - set(TOOL_PERMISSIONS))
    if missing_explicit_permissions:
        errors.append("missing explicit permissions: " + ", ".join(missing_explicit_permissions))

    errors.extend(_referenced_tool_errors())
    return errors


def _referenced_tool_errors() -> list[str]:
    """Every tool named in a side table must exist, and every tool must be selectable."""
    known = set(TOOL_REGISTRY)
    references = {
        "cache.TOOL_CACHE_TTLS": set(cache.TOOL_CACHE_TTLS),
        "cache.UNCACHEABLE_TOOLS": set(cache.UNCACHEABLE_TOOLS),
        "cache.INVALIDATION_MAP": set(cache.INVALIDATION_MAP)
        | {t for targets in cache.INVALIDATION_MAP.values() for t in targets},
        "hardening.TOOL_TIMEOUTS": set(hardening.TOOL_TIMEOUTS),
        "permissions.TOOL_PERMISSIONS": set(TOOL_PERMISSIONS),
        "coordinator._AGENT_TOOLS": {t for tools in coordinator._AGENT_TOOLS.values() for t in tools},
        "tool_selector.TOOL_GROUPS": {t for tools in tool_selector.TOOL_GROUPS.values() for t in tools},
        "tool_selector.COMMON_TOOLS": set(tool_selector.COMMON_TOOLS),
    }
    errors = [
        f"{table} names unknown tool(s): {', '.join(sorted(names - known))}"
        for table, names in references.items()
        if names - known
    ]
    selectable = references["tool_selector.TOOL_GROUPS"] | references["tool_selector.COMMON_TOOLS"]
    if known - selectable:
        errors.append("tools no keyword group can select: " + ", ".join(sorted(known - selectable)))
    return errors


def main() -> int:
    errors = validate_tool_contracts()
    if errors:
        print("Tool contract validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"Tool contract validation passed ({len(TOOL_REGISTRY)} tools).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
