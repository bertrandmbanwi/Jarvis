#!/usr/bin/env python3
"""Offline golden-case evals for routing, safety, and permissions."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.core.hardening import check_dangerous_command  # noqa: E402
from jarvis.core.permissions import assess_tool_call  # noqa: E402


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("eval file must contain a list at 'cases'")
    return cases


def _run_dangerous_command(case: dict[str, Any]) -> tuple[bool, str]:
    warning = check_dangerous_command(str(case["input"]))
    blocked = warning is not None
    expected = bool(case["expect_blocked"])
    return blocked == expected, f"blocked={blocked}, expected={expected}, warning={warning}"


def _run_permission(case: dict[str, Any]) -> tuple[bool, str]:
    original_mode = os.environ.get("JARVIS_TOOL_PERMISSION_MODE")
    os.environ["JARVIS_TOOL_PERMISSION_MODE"] = str(case.get("mode", "audit"))
    try:
        decision = assess_tool_call(str(case["tool"]), dict(case.get("input", {})))
    finally:
        if original_mode is None:
            os.environ.pop("JARVIS_TOOL_PERMISSION_MODE", None)
        else:
            os.environ["JARVIS_TOOL_PERMISSION_MODE"] = original_mode
    expected = bool(case["expect_allowed"])
    return decision.allowed == expected, f"allowed={decision.allowed}, expected={expected}"


def _run_planner_route(case: dict[str, Any]) -> tuple[bool, str]:
    # Private helper is intentionally eval-covered to lock routing regressions.
    from jarvis.core.brain import _is_chat_only

    chat_only = _is_chat_only(str(case["input"]))
    expected = bool(case["expect_chat_only"])
    return chat_only == expected, f"chat_only={chat_only}, expected={expected}"


RUNNERS = {
    "dangerous_command": _run_dangerous_command,
    "permission": _run_permission,
    "planner_route": _run_planner_route,
}


def run_evals(path: Path) -> list[str]:
    failures: list[str] = []
    for case in _load_cases(path):
        case_id = str(case.get("id", "<missing-id>"))
        runner = RUNNERS.get(str(case.get("type", "")))
        if runner is None:
            failures.append(f"{case_id}: unknown eval type {case.get('type')!r}")
            continue
        passed, detail = runner(case)
        if not passed:
            failures.append(f"{case_id}: {detail}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run JARVIS offline evals.")
    parser.add_argument("--offline", action="store_true", help="Accepted for CI readability; all evals are offline.")
    parser.add_argument("--cases", default=str(ROOT / "evals" / "golden_cases.yml"))
    args = parser.parse_args()

    failures = run_evals(Path(args.cases))
    if failures:
        print("Eval failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All offline evals passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
