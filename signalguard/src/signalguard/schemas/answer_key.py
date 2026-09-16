"""
Hidden benchmark answer-key schema for SignalGuard.

ANSWER-KEY ISOLATION (locked decision, not optional):
This module, and anything written under `benchmark/answer_key/`, must
NEVER be imported by retrieval, structured-extraction, tool-calling, or
pipeline code. It is read only by the Day-5 evaluation harness. When the
pipeline package exists, add a static-analysis test that fails the build
if any non-evaluation module imports from here.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

DefectTier = Literal["tier1", "tier2"]


class AnswerKeyEntry(BaseModel):
    defect_id: str
    tier: DefectTier
    defect_type: str
    rule_id: Optional[str] = None  # e.g. "R1", "R2", "R5"; None for tier1
    account_id: str
    affected_event_ids: List[str]
    affected_ref_id: Optional[str] = None
    expected_tool: Optional[str] = None  # None for tier1 (no LLM tool call needed)
    expected_doc_chunk_ids: Optional[List[str]] = None  # filled in once doc corpus exists (Day 3)
    description: str