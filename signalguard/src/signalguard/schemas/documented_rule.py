"""
DocumentedRule and ExtractionResult schemas for SignalGuard.

DocumentedRule is Capability 2's structured-extraction target: the typed object a documentation-grounded LLM call
produces from prose. ExtractionResult wraps it with an explicit status, so abstention (INSUFFICIENT_EVIDENCE /
AMBIGUOUS) is a first-class outcome, not an error case bolted on after.

rule_id here is assigned BY THE EXTRACTION CALL ITSELF (a short slut the model invets) -- it is intentionally NOT
the same namespace as the hidden R1-R5 identifiers used internall by the corruption benchmark. Those never appear
in the doc corpus text and must never leak into anything the model sees or produces. Evaluation matches an extracted
rule back to its gold R-id via source_location (chunk_id) and rule_type, never by comparing rule_id strings.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

class RuleType(str, Enum):
    PREREQUISITE = "prerequisite"
    TEMPORAL_ORDER = "temporal_order"
    TIMING_WINDOW = "timing_window"
    OTHER = "other"

class DocumentedRule(BaseModel):
    rule_id: str = Field(
        description="A short identifier for this rule, invented by the extractor "
        "(e.g. a slug of the condition). NOT a reference to any internal benchmark rule ID."
    )
    rule_type: RuleType
    relevant_events: List[str] = Field(
        description="Event type strings (e.g., 'session.booked') this rule concerns."
    )
    condition: str = Field(description="Plain-language statement of the rule, as documented.")
    prerequisite: Optional[str] = Field(
        default=None, description="The event that must precede another, if this is a prerequisite rule."
    )
    temporal_constraint: Optional[str] = Field(
        default=None, description="A timing constraint, e.g., 'within 7 days', if this is a timing-window rule."
    )
    source_document: str = Field(description="The source markdown filename this rule was extracted from.")
    source_location: str = Field(description="The exact chunk_id of the excerpt that support this rule.")
    confidence: str = Field(description="Model-reported confidence (e.g., 'high', 'medium', 'low'). NOT a " \
    "calibrated probability")
    requires_tool: Optional[str] = Field(
        default=None, description="The bounded tool name expected to evaluate this rule against data, if known."
    )
    notes: Optional[str] = Field(default=None)

class ExtractionStatus(str, Enum):
    DOCUMENTED = "documented"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    AMBIGUOUS = "ambiguous"

class ExtractionResult(BaseModel):
    status: ExtractionStatus
    rule: Optional[DocumentedRule] = Field(default=None, description="Populated only when status == 'documented'.")
    reasoning: str = Field(description="Brief explanation of the finding, especially important when abstaining.")