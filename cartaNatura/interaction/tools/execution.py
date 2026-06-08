"""Tool execution helpers."""

from __future__ import annotations

from typing import Any

from .contracts import ToolName
from .registry import ToolRegistry


def execute_tool(
    registry: ToolRegistry,
    tool_name: ToolName,
    **kwargs: Any,
) -> dict[str, Any]:
    return registry.execute(tool_name, **kwargs)
