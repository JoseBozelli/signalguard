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


def investigate_record(
    candidate_record: Record,
    all_records: List[Record],
    retrieve_fn: Callable[[str], List[Any]],
    reasoner: Optional[Reasoner] = None,
) -> Optional[Finding]:
    """
    Runs the full System B pipeline for one candidate record.

    Returns None in two distinct "nothing to report" cases -- the model
    correctly abstained (insufficient evidence / ambiguous), or the tool
    checked the rule and found no violation -- and a Finding only when a
    documented rule was extracted AND the tool confirmed a violation.
    """
    event_type = candidate_record.get("event_type")
    question = _QUESTION_MAP.get(event_type)
    if question is None:
        return None  # no canonical investigation defined for this event type

    if reasoner is None:
        reasoner = get_reasoner()

    chunks = retrieve_fn(question)
    extraction = extract_rule(question, chunks, reasoner=reasoner)

    if extraction.status != ExtractionStatus.DOCUMENTED or extraction.rule is None:
        return None  # correctly abstained; nothing to report

    rule = extraction.rule
    ref_id = candidate_record.get("ref_id")
    related_ref_id = candidate_record.get("related_ref_id")

    _tool_name, tool_result = select_and_execute_tool(
        rule, ref_id, all_records, related_ref_id=related_ref_id, reasoner=reasoner
    )

    if not tool_result.violated:
        return None  # rule checked, no violation found

    account_id = candidate_record.get("account_id")
    return Finding(
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
        recommended_action=f"Review {event_type} record for ref_id={ref_id}: {tool_result.reason}",
    )