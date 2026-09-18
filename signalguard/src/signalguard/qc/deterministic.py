"""
Deterministic QC baseline (Baseline A) for SignalGuard.

This module intentionally knows NOTHING about the documented business
rules. It only performs record-level structural checks: things
Python can establish with zero interpretation. This is what makes it a
fair baseline to compare System B (the documentation-grounded AI
pipeline) against -- Baseline A represents "what you get with schema
validation alone, no reading of the docs."

The rule-checking logic is deliberately NOT here. It is built as bounded tools 
the AI pipeline calls only after retrieving and extracting the relevant rule from the doc corpus.
"""

from __future__ import annotations

from typing import Dict, List

from signalguard.schemas.event import EventType
from signalguard.schemas.finding import Finding

Record = Dict[str, object]

_VALID_EVENT_TYPES = {e.value for e in EventType}


def check_duplicate_event_ids(records: List[Record]) -> List[Finding]:
    seen_ids: set = set()
    already_reported: set = set()
    findings: List[Finding] = []

    for record in records:
        event_id = record.get("event_id")
        if event_id in seen_ids and event_id not in already_reported:
            findings.append(
                Finding(
                    source="deterministic_qc",
                    tier="tier1",
                    defect_type="duplicate_event_id",
                    account_id=str(record.get("account_id")) if record.get("account_id") else None,
                    affected_event_ids=[str(event_id)],
                    evidence=f"event_id '{event_id}' appears on more than one record.",
                    reasoning_category="fact",
                    recommended_action="Investigate ingestion pipeline for duplicate delivery or ID collision.",
                )
            )
            already_reported.add(event_id)
        seen_ids.add(event_id)

    return findings


def check_missing_account_id(records: List[Record]) -> List[Finding]:
    findings: List[Finding] = []
    for record in records:
        if not record.get("account_id"):
            findings.append(
                Finding(
                    source="deterministic_qc",
                    tier="tier1",
                    defect_type="missing_account_id",
                    account_id=None,
                    affected_event_ids=[str(record.get("event_id"))],
                    evidence=f"Record {record.get('event_id')} has a null or empty account_id.",
                    reasoning_category="fact",
                    recommended_action="Trace record back through the ingestion pipeline to recover account_id.",
                )
            )
    return findings


def check_invalid_event_type(records: List[Record]) -> List[Finding]:
    findings: List[Finding] = []
    for record in records:
        event_type = record.get("event_type")
        if event_type not in _VALID_EVENT_TYPES:
            findings.append(
                Finding(
                    source="deterministic_qc",
                    tier="tier1",
                    defect_type="invalid_event_type",
                    account_id=str(record.get("account_id")) if record.get("account_id") else None,
                    affected_event_ids=[str(record.get("event_id"))],
                    evidence=f"event_type '{event_type}' is not one of the recognized event types.",
                    reasoning_category="fact",
                    recommended_action="Confirm whether this reflects an unannounced upstream schema change.",
                )
            )
    return findings


def run_baseline_qc(records: List[Record]) -> List[Finding]:
    """Run all deterministic Tier-1 checks and return the combined findings."""
    findings: List[Finding] = []
    findings.extend(check_duplicate_event_ids(records))
    findings.extend(check_missing_account_id(records))
    findings.extend(check_invalid_event_type(records))
    return findings