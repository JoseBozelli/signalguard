"""
End-to-end orchestration for SignalGuard's documentation-grounded
detection pipeline (System B): retrieve -> extract -> (if documented)
select and execute a bounded tool -> Finding.

retrieve_fn is injected rather than this module calling
signalguard.rag.index.retrieve directly, so orchestration logic (question
routing, abstention handling, violation branching, Finding construction)
can be tested without a real vector-DB backend. Callers wire retrieve_fn
to whatever retrieval implementation they use, e.g.
`lambda question: retrieve(collection, question, embedder, k=3)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from signalguard.extraction.rule_extraction import extract_rule
from signalguard.llm.reasoner import Reasoner, get_reasoner
from signalguard.schemas.documented_rule import ExtractionStatus
from signalguard.schemas.finding import Finding
from signalguard.tools.tool_selection import select_and_execute_tool

Record = Dict[str, Any]

# Canonical investigation question per event type. Deliberately scoped to
# the project's locked rule set (R1, R2, R5) -- not a generic "ask about
# anything" mechanism, this reflects exactly the benchmark that was built
# and is being measured.
_QUESTION_MAP: Dict[str, str] = {
    "session.completed": "Does a completed session require a preceding booking event, and if so what is the rule?",
    "session.no_show": "Does a session outcome require a preceding booking event, and if so what is the rule?",
    "task.completed": (
        "Is there a documented rule about the required order between a task being "
        "required and a task being completed?"
    ),
    "followup.required": (
        "Is there a maximum allowed number of days between a session no-show and the "
        "required follow-up?"
    ),
}

# Public export: which event types investigate_record() actually knows how
# to investigate. Callers building candidate lists (e.g. from an answer
# key with multiple affected_event_ids per entry) should pick a record
# whose event_type is in this set, rather than assuming any given index.
INVESTIGABLE_EVENT_TYPES = frozenset(_QUESTION_MAP.keys())

def pick_investigable_candidate(affected_event_ids: List[str], records_by_id: Dict[str, Record]) -> Optional[Record]:
    """
    An answer-key entry may list more than one affected_event_id (e.g., the bad_ordering/R2 defect lists both the task.
    required and task.completed records, since the injector swaps both their timestamps). Picks whichever affected record's
    event_type is actually investigable, rather than assuming a fixed index is always correct. Falls back to the first
    ID if none are investigable, so a caller sees a clear miss rather than a silent skip.
    """
    for event_id in affected_event_ids:
        record = records_by_id.get(event_id)
        if record and record.get("event_type") in INVESTIGABLE_EVENT_TYPES:
            return record
    return records_by_id.get(affected_event_ids[0]) if affected_event_ids else None

def investigate_record(
    candidate_record: Record,
    all_records: List[Record],
    retrieve_fn: Callable[[str], List[Any]],
    reasoner: Optional[Reasoner] = None,
) -> Optional[Finding]:
    """
    Runs the full System B pipeline for one candidate record and returns only the final Finding (or None).
    Thin wrapper over investigate_record_with_trace() for callers that don't need the intermediate detail --
    the evaluation runner uses the trace version directly.
    """
    return investigate_record_with_trace(candidate_record, all_records, retrieve_fn, reasoner).finding

@dataclass
class InvestigationTrace:
    """
    Full visibility into one invetigate_record run -- every intermediate stage, not jus the final Finding.
    This is what the evaluation runner needs (which chunks were retrieved, whether the model documented/
    abstained, which tool it picked) and doubles as the shape JSONL tracing will eventually persist per
    investigation.
    """

    event_type: Optional[str] = None
    question: Optional[str] = None
    retrieved_chunk_ids: List[str] = field(default_factory=list)
    extraction_status: Optional[str] = None     # "documented" / "insufficient_evidence" / "ambiguous"
    extracted_rule_id: Optional[str] = None
    selected_tool: Optional[str] = None
    tool_violated: Optional[str] = None
    finding: Optional[Finding] = None

def investigate_record_with_trace(
        candidate_record: Record,
        all_records: List[Record],
        retrieve_fn: Callable[[str], List[Any]],
        reasoner: Optional[Reasoner] = None
) -> InvestigationTrace:
    """
    Same pipeline as investigate_record(), but returns full intermediate visibility rather than only the final Finding.
    """
    event_type = candidate_record.get("event_type")
    trace = InvestigationTrace(event_type=event_type)

    question = _QUESTION_MAP.get(event_type)
    if question is None:
        return trace    # no canonical investigation defined for this event type
    trace.question = question

    if reasoner is None:
        reasoner = get_reasoner()

    chunks = retrieve_fn(question)
    trace.retrieved_chunk_ids = [getattr(c, "chunk_id", None) for c in chunks]

    extraction = extract_rule(question, chunks, reasoner=reasoner)
    trace.extraction_status = extraction.status.value if hasattr(extraction.status, "value") else str(extraction.status)

    if extraction.status != ExtractionStatus.DOCUMENTED or extraction.rule is None:
        return trace    # correctly abstained; nothing further to report

    rule = extraction.rule
    trace.extracted_rule_id = rule.rule_id
    ref_id = candidate_record.get("ref_id")
    related_ref_id = candidate_record.get("related_ref_id")

    tool_name, tool_result = select_and_execute_tool(
        rule, ref_id, all_records, related_ref_id=related_ref_id, reasoner=reasoner
    )
    trace.selected_tool = tool_name
    trace.tool_violated = tool_result.violated

    if not tool_result.violated:
        return trace    # rule checked, no violation found

    account_id = candidate_record.get("account_id")
    trace.finding = Finding(
        source="ai_pipeline",
        tier="tier2",
        defect_type=rule.rule_type.value,
        account_id=str(account_id) if account_id else None,
        affected_event_ids=[str(candidate_record.get("event_id"))],
        affected_ref_id=ref_id,
        rule_id=rule.rule_id,
        evidence=tool_result.reason,
        reasoning_category="documented_rule",
        confidence=rule.confidence,
        recommended_action=f"Review {event_type} record for ref_id={ref_id}: {tool_result.reason}"
    )
    return trace