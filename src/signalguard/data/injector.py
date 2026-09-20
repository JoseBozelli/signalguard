"""
Controlled corruption injector for SignalGuard.

Takes the clean, rule-compliant Event list from `generator.py` and produces:

  1. a corrupted record set (plain dicts, NOT validated Event objects --
     some Tier-1 defects are intentionally schema-invalid, which is the
     whole point of testing deterministic QC / schema validation against
     them; a Pydantic Event would reject a missing account_id at
     construction time)
  2. a hidden answer key (AnswerKeyEntry list) recording exactly what was
     corrupted, which rule it violates (Tier 2 only), and which tool is
     expected to catch it

Design note: every injector function shares a single `used` set of
event_ids across the whole run, so no two injected defects land on the
same record or lifecycle -- this keeps each answer-key entry unambiguous,
which matters for interpretability early in the project.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
from uuid import uuid4

from signalguard.schemas.answer_key import AnswerKeyEntry
from signalguard.schemas.event import Event, EventType

RULE_TOOL_MAP = {
    "R1": "check_prerequisite",
    "R2": "check_event_order",
    "R3": "check_prerequisite",
    "R4": "check_event_order",
    "R5": "calculate_interval",
}

# Gold retrieval labels: rule_id -> chunk_id(s), where chunk_id follows the
# locked chunking convention "<doc_filename>::<section-heading-slug>"
# (one chunk per markdown ## section). This mapping is answer-key
# construction data -- it is never read by retrieval/reasoning code, only
# by the injector (to populate AnswerKeyEntry.expected_doc_chunk_ids) and
# later by the evaluation harness.
RULE_CHUNK_MAP = {
    "R1": ["event-lifecycle-rules.md::session-booking-and-completion"],
    "R2": ["event-lifecycle-rules.md::task-completion-requirements"],
    "R3": ["event-lifecycle-rules.md::follow-up-completion-requirements"],
    "R4": ["event-lifecycle-rules.md::follow-up-completion-requirements"],
    "R5": ["sla-and-timing-policies.md::follow-up-response-window-after-a-missed-session"],
}

Record = Dict[str, object]


def _records_from_events(events: List[Event]) -> List[Record]:
    return [e.to_dict() for e in events]


def _group_by_ref_id(records: List[Record]) -> Dict[str, List[Record]]:
    groups: Dict[str, List[Record]] = {}
    for r in records:
        ref_id = r.get("ref_id")
        if ref_id is not None:
            groups.setdefault(str(ref_id), []).append(r)
    return groups


# ---------------------------------------------------------------------------
# Tier 1: record-level, deterministically detectable defects
# ---------------------------------------------------------------------------

def _inject_duplicate_event_id(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    candidates = [i for i, r in enumerate(records) if r["event_id"] not in used]
    idx_a, idx_b = rng.sample(candidates, 2)
    original_b_id = records[idx_b]["event_id"]
    records[idx_b]["event_id"] = records[idx_a]["event_id"]
    used.add(records[idx_a]["event_id"])
    used.add(original_b_id)
    entry = AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier1",
        defect_type="duplicate_event_id",
        account_id=str(records[idx_a]["account_id"]),
        affected_event_ids=[str(records[idx_a]["event_id"]), str(original_b_id)],
        description=(
            f"Record originally event_id={original_b_id} was overwritten to share "
            f"event_id={records[idx_a]['event_id']} with another record."
        ),
    )
    return records, entry


def _inject_missing_account_id(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    candidates = [i for i, r in enumerate(records) if r["event_id"] not in used]
    idx = rng.choice(candidates)
    original_account = records[idx]["account_id"]
    records[idx]["account_id"] = None
    used.add(records[idx]["event_id"])
    entry = AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier1",
        defect_type="missing_account_id",
        account_id=str(original_account),
        affected_event_ids=[str(records[idx]["event_id"])],
        description=f"account_id removed from record {records[idx]['event_id']} (originally {original_account}).",
    )
    return records, entry


def _inject_invalid_event_type(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    candidates = [i for i, r in enumerate(records) if r["event_id"] not in used]
    idx = rng.choice(candidates)
    original_type = records[idx]["event_type"]
    records[idx]["event_type"] = "session.rescheduled"  # not in the 8 locked types
    used.add(records[idx]["event_id"])
    entry = AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier1",
        defect_type="invalid_event_type",
        account_id=str(records[idx]["account_id"]),
        affected_event_ids=[str(records[idx]["event_id"])],
        description=f"event_type changed from '{original_type}' to an undocumented value ('session.rescheduled').",
    )
    return records, entry


# ---------------------------------------------------------------------------
# Tier 2: documentation-dependent defects
# ---------------------------------------------------------------------------

def _inject_missing_prerequisite(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    """Violates R1: remove a session.booked whose ref_id has a session.completed."""
    groups = _group_by_ref_id(records)
    eligible = [
        ref_id
        for ref_id, recs in groups.items()
        if any(r["event_type"] == EventType.SESSION_COMPLETED.value for r in recs)
        and any(r["event_type"] == EventType.SESSION_BOOKED.value for r in recs)
        and all(r["event_id"] not in used for r in recs)
    ]
    ref_id = rng.choice(eligible)
    booked = next(r for r in records if r.get("ref_id") == ref_id and r["event_type"] == EventType.SESSION_BOOKED.value)
    completed = next(r for r in records if r.get("ref_id") == ref_id and r["event_type"] == EventType.SESSION_COMPLETED.value)
    records.remove(booked)
    used.add(completed["event_id"])
    used.add(booked["event_id"])
    return records, AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier2",
        defect_type="missing_prerequisite",
        rule_id="R1",
        account_id=str(completed["account_id"]),
        affected_event_ids=[str(completed["event_id"])],
        affected_ref_id=ref_id,
        expected_tool=RULE_TOOL_MAP["R1"],
        expected_doc_chunk_ids=RULE_CHUNK_MAP["R1"],
        description=f"session.completed (ref_id={ref_id}) has no preceding session.booked; the booked record was removed.",
    )


def _inject_bad_ordering(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    """Violates R2: swap timestamps so task.completed precedes task.required."""
    groups = _group_by_ref_id(records)
    eligible = [
        ref_id
        for ref_id, recs in groups.items()
        if any(r["event_type"] == EventType.TASK_REQUIRED.value for r in recs)
        and any(r["event_type"] == EventType.TASK_COMPLETED.value for r in recs)
        and all(r["event_id"] not in used for r in recs)
    ]
    ref_id = rng.choice(eligible)
    required = next(r for r in records if r.get("ref_id") == ref_id and r["event_type"] == EventType.TASK_REQUIRED.value)
    completed = next(r for r in records if r.get("ref_id") == ref_id and r["event_type"] == EventType.TASK_COMPLETED.value)
    required["timestamp"], completed["timestamp"] = completed["timestamp"], required["timestamp"]
    used.add(required["event_id"])
    used.add(completed["event_id"])
    return records, AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier2",
        defect_type="bad_ordering",
        rule_id="R2",
        account_id=str(required["account_id"]),
        affected_event_ids=[str(required["event_id"]), str(completed["event_id"])],
        affected_ref_id=ref_id,
        expected_tool=RULE_TOOL_MAP["R2"],
        expected_doc_chunk_ids=RULE_CHUNK_MAP["R2"],
        description=f"task.completed timestamp swapped to precede task.required for ref_id={ref_id}.",
    )


def _inject_timing_window_violation(
    records: List[Record], rng: random.Random, used: Set[str]
) -> Tuple[List[Record], AnswerKeyEntry]:
    """Violates R5: push followup.required beyond the 7-day SLA from its triggering no_show."""
    candidates = [
        r for r in records
        if r["event_type"] == EventType.FOLLOWUP_REQUIRED.value and r["event_id"] not in used
    ]
    record = rng.choice(candidates)
    original_ts = record["timestamp"]
    no_show = next(
        r for r in records
        if r["event_type"] == EventType.SESSION_NO_SHOW.value and r.get("ref_id") == record["related_ref_id"]
    )
    no_show_ts = datetime.fromisoformat(str(no_show["timestamp"]))
    record["timestamp"] = (no_show_ts + timedelta(days=10)).isoformat()  # 10d > 7d SLA
    used.add(record["event_id"])
    return records, AnswerKeyEntry(
        defect_id=str(uuid4()),
        tier="tier2",
        defect_type="timing_window_violation",
        rule_id="R5",
        account_id=str(record["account_id"]),
        affected_event_ids=[str(record["event_id"])],
        affected_ref_id=str(record["ref_id"]),
        expected_tool=RULE_TOOL_MAP["R5"],
        expected_doc_chunk_ids=RULE_CHUNK_MAP["R5"],
        description=(
            f"followup.required (ref_id={record['ref_id']}) moved from {original_ts} to "
            f"{record['timestamp']}, 10 days after its triggering no_show (exceeds 7-day SLA)."
        ),
    )


_TIER1_INJECTORS = [_inject_duplicate_event_id, _inject_missing_account_id, _inject_invalid_event_type]
_TIER2_INJECTORS = [_inject_missing_prerequisite, _inject_bad_ordering, _inject_timing_window_violation]


def inject_defects(
    events: List[Event],
    seed: int = 7,
    instances_per_defect_type: int = 5,
) -> Tuple[List[Record], List[AnswerKeyEntry]]:
    """Corrupt a copy of the clean dataset. Returns (corrupted_records, answer_key)."""
    rng = random.Random(seed)
    records = _records_from_events(events)
    used: Set[str] = set()
    answer_key: List[AnswerKeyEntry] = []

    for injector_fn in _TIER1_INJECTORS + _TIER2_INJECTORS:
        for _ in range(instances_per_defect_type):
            records, entry = injector_fn(records, rng, used)
            answer_key.append(entry)

    return records, answer_key