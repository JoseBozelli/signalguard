"""
ToolResult schem for SignalGuard's bounded tool-calling layer.

The shape is deliberately generic (tool_name, violated, reason, evidence) rather than one schema per tool --
any deterministic check that reduces to a pass/fail veridict with supporting evidence fits this, regardless of
which specific rule or event vocabulary it belongs to.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field

class ToolResult(BaseModel):
    tool_name: str
    violated: bool
    reason: str
    evidence: Dict[str, Any] = Field(default_factory=dict)