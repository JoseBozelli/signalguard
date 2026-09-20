"""
Bounded deterministic tool functions for SignalGuar's tool-calling layer (Capability 3).

Python performs the exact calculations here -- never the LLM (the project's core deterministic/LLM separation
principle). The LLM's role, built in the next step, is only to select which of these tools applies to a given
DocumentedRule and supply its arguments; execution and the pass/fail veridict are entirely deterministic and
reproducible from that point on.

All three functions operate on plain event_type strings, ref_id, and timestamps. None of them import SignalGuard's
EventType vocabulary or assume any specific event names -- the tool mechanic itself is domain-neutral and reusable
by a future event vocabulary; only the arguments passed to it (by orchestration, from a specific DocumentedRule) are
SignalGuard-specific.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from signalguard.schemas.tool_result import ToolResult

Record = Dict[str, object]

def _records_for_ref(records: List[Record], ref_id: str) -> List[Record]:
    return [r for r in records if r.get("ref_id") == ref_id]

def _find_event(records: List[Record], event_type: str) -> Optional[Record]:
    return next((r for r in records if r.get("event_type") == event_type), None)

def _parse_ts(record: Record) -> datetime:
    ts = record["timestamp"]
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))

def check_prerequisites(
        records: List[Record],
        ref_id: str,
        prerequisite_event_type: str,
        dependent_event_type: str,
) -> ToolResult:
    """
    Checks whether `prerequisite_event_type` is PRESENT for ref_id whenever `dependent_event_type` is present.
    Presence only -- the ordering between the two, if both are present, is check_event_order's concern, not this
    tool's.
    """
    same_ref = _records_for_ref(records, ref_id)
    dependent = _find_event(same_ref, dependent_event_type)
    if dependent is None:
        return ToolResult(
            tool_name="check_prerequisite",
            violated=False,
            reason=f"No '{dependent_event_type}' record exists for ref_id={ref_id}; nothing to check.",
            evidence={"ref_id": ref_id, "dependent_event_type": dependent_event_type}
        )

    prerequisite = _find_event(same_ref, prerequisite_event_type)
    if prerequisite is None:
        return ToolResult(
            tool_name="check_prerequisite",
            violated=True,
            reason=(
                f"'{dependent_event_type}' exists for ref_id={ref_id} but no "
                f"'{prerequisite_event_type}' record is present."
            ),
            evidence={
                "ref_id": ref_id,
                "prerequisite_event_type": prerequisite_event_type,
                "dependent_event_type": dependent_event_type,
            },
        )

    return ToolResult(
        tool_name="check_prerequisite",
        violated=False,
        reason=f"'{prerequisite_event_type}' is present for ref_id={ref_id}.",
        evidence={"ref_id": ref_id}
    )

def check_event_order(
        records: List[Record],
        ref_id: str,
        first_event_type: str,
        second_event_type: str,
) -> ToolResult:
    """
    Given both events exist for ref_id, checks that `first_event_type's`'s timestamp is at or before `second_event_
    type`'s. Does not check whether either event is present at all -- check_prerequisite's job.
    """
    same_ref = _records_for_ref(records, ref_id)
    first = _find_event(same_ref, first_event_type)
    second = _find_event(same_ref, second_event_type)

    if first is None or second is None:
        missing = first_event_type if first is None else second_event_type
        return ToolResult(
            tool_name="check_event_order",
            violated=False,
            reason=f"'{missing}' is not present for ref_id={ref_id}; ordering cannot be checked.",
            evidence={"ref_id": ref_id}
        )

    first_ts, second_ts = _parse_ts(first), _parse_ts(second)
    if first_ts > second_ts:
        return ToolResult(
            tool_name="check_event_order",
            violated=True,
            reason=(
                f"'{first_event_type}' ({first_ts}) occurs after "
                f"'{second_event_type}' ({second_ts}) for ref_id={ref_id}."
            ),
            evidence={"ref_id": ref_id, "first_timestamp": str(first_ts), "second_timestamp": str(second_ts)},
        )

    return ToolResult(
        tool_name="check_event_order",
        violated=False,
        reason=f"'{first_event_type}' correctly precedes '{second_event_type}' for ref_id={ref_id}.",
        evidence={"ref_id": ref_id}
    )

def calculate_interval(
        records: List[Record],
        ref_id: str,
        related_ref_id: str,
        event_type: str,
        related_event_type: str,
        max_days: float
) -> ToolResult:
    """
    Computes the interval in days between an event identified by (ref_id, event_type) and a related event identified
    by (related_ref_id, related_event_type), and checks it against max_days.
    """
    target = _find_event(_records_for_ref(records, ref_id), event_type)
    related = _find_event(_records_for_ref(records, related_ref_id), related_event_type)

    if target is None or related is None:
        return ToolResult(
            tool_name="calculate_interval",
            violated=False,
            reason="One or both events are missing; interval cannot be calculated.",
            evidence={"ref_id": ref_id, "related_ref_id": related_ref_id}
        )

    delta_days = (_parse_ts(target) - _parse_ts(related)).days
    violated = delta_days > max_days

    return ToolResult(
        tool_name="calculate_interval",
        violated=violated,
        reason=(
            f"Interval between '{related_event_type}' and '{event_type}' is {delta_days} day(s), "
            f"{'exceeding' if violated else 'within'} the {max_days}-day limit."
        ),
        evidence={
            "ref_id": ref_id,
            "related_ref_id": related_ref_id,
            "delta_days": delta_days,
            "max_days": max_days
        },
    )