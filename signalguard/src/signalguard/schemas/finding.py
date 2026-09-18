"""
Finding schema for SignalGuard.

A Finding is the unit of output for both the deterministic QC baseline
and the documentation-grounded AI pipeline. Keeping one
shared shape means System B extends this schema later rather than
inventing a second output format.

`reasoning_category` encodes the epistemic separation required by the
project spec:
  - "fact": directly observable from the data, no interpretation needed
    (this is all deterministic QC ever produces)
  - "documented_rule": supported by retrieved documentation (AI pipeline)
  - "ai_interpretation": a model inference that is NOT itself an
    authoritative rule (AI pipeline; must never be silently promoted to
    documented_rule)
"""

from __future__ import annotations

from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

FindingSource = Literal["deterministic_qc", "ai_pipeline"]
DefectTier = Literal["tier1", "tier2"]
ReasoningCategory = Literal["fact", "documented_rule", "ai_interpretation"]


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    source: FindingSource
    tier: DefectTier
    defect_type: str
    account_id: Optional[str] = None
    affected_event_ids: List[str]
    affected_ref_id: Optional[str] = None
    rule_id: Optional[str] = None  # None for deterministic_qc findings
    evidence: str
    reasoning_category: ReasoningCategory
    confidence: Optional[str] = None  # model-reported only; None for deterministic (certain)
    recommended_action: str