"""JSON schemas for structured model outputs.

They follow the strict structured-output rules (every property required,
``additionalProperties: false``) so OpenAI can guarantee conforming JSON.
Ollama accepts the same schemas through its ``format`` field.
"""
from typing import Any


def _object(properties: dict[str, Any], title: str) -> dict[str, Any]:
    return {
        "title": title,
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


COMPLEXITY_SCHEMA = _object(
    {"verdict": {"type": "string", "enum": ["simple", "complex"]}},
    "complexity_verdict",
)

PLAN_SCHEMA = _object(
    {
        "needs_decomposition": {"type": "boolean"},
        "reason": {"type": "string"},
        "goal_summary": {"type": "string"},
        "subtasks": {
            "type": "array",
            "items": _object(
                {"title": {"type": "string"}, "description": {"type": "string"}},
                "subtask",
            ),
        },
    },
    "task_plan",
)

QA_SCHEMA = _object(
    {
        "passed": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "qa_verdict",
)

PLANNING_DECISION_SCHEMA = _object(
    {
        "needs_planning": {"type": "boolean"},
        "confidence": {"type": "number"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "planning_decision",
)
