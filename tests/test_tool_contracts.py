"""Contract tests for the tool registry and permission catalog."""
from scripts.check_tool_contracts import validate_tool_contracts


def test_tool_contracts_are_complete():
    assert validate_tool_contracts() == []
