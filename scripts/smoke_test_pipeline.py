"""
Manual smoke test / mini-evaluation for the full System B pipeline
(retrieve -> extract -> select tool -> execute -> Finding). NOT a pytest
test -- makes real, billed calls to Voyage and Claude, and results are
non-deterministic. This is a first, hand-run measurement, not the formal
Day-5 evaluation harness.

Runs the pipeline against:
  1. Every real Tier-2 defect in the corrupted benchmark -- each SHOULD
     produce a Finding. This is System B's actual Tier-2 recall, directly
     comparable to Baseline A's measured 0%.
  2. A sample of clean lifecycles of the same event types -- each SHOULD
     produce no Finding. This is a false-positive check.

Usage:
    uv run python scripts/smoke_test_pipeline.py
"""

from pathlib import Path

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects
from signalguard.pipeline.orchestrator import INVESTIGABLE_EVENT_TYPES, investigate_record
from signalguard.rag.chunking import chunk_corpus
from signalguard.rag.embeddings import get_embedder
from signalguard.rag.index import build_index, retrieve

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"


def _pick_candidate(entry, records_by_id):
    """
    An answer-key entry may list more than one affected_event_id (e.g. the
    bad_ordering/R2 defect lists both the task.required and task.completed
    records, since the injector swaps both their timestamps). Pick
    whichever affected record's event_type is actually investigable,
    rather than assuming index [0] is always the right one.
    """
    for event_id in entry.affected_event_ids:
        record = records_by_id.get(event_id)
        if record and record.get("event_type") in INVESTIGABLE_EVENT_TYPES:
            return record
    # Fallback: none of the affected records are investigable by this
    # pipeline's current event-type coverage -- return the first anyway so
    # the caller can see a clear MISSED rather than a silent skip.
    return records_by_id[entry.affected_event_ids[0]]


def main():
    embedder = get_embedder()
    collection = build_index(DOCS_DIR, embedder)
    retrieve_fn = lambda question: retrieve(collection, question, embedder, k=3)  # noqa: E731

    events = generate_clean_dataset(num_accounts=80, seed=42)
    records, answer_key = inject_defects(events, seed=7, instances_per_defect_type=5)
    records_by_id = {r["event_id"]: r for r in records}

    tier2_entries = [e for e in answer_key if e.tier == "tier2"]
    defect_ref_ids = {e.affected_ref_id for e in answer_key if e.affected_ref_id}

    print(f"\n{'=' * 70}\nPART 1: Tier-2 RECALL -- {len(tier2_entries)} known defects\n{'=' * 70}")
    caught = 0
    for entry in tier2_entries:
        candidate = _pick_candidate(entry, records_by_id)
        finding = investigate_record(candidate, records, retrieve_fn)
        status = "CAUGHT" if finding else "MISSED"
        if finding:
            caught += 1
        print(f"  [{status}] rule_id={entry.rule_id}  ref_id={entry.affected_ref_id}  defect_type={entry.defect_type}")
        if finding:
            print(f"           -> {finding.evidence}")
    print(f"\nTier-2 recall: {caught}/{len(tier2_entries)}")

    print(f"\n{'=' * 70}\nPART 2: FALSE POSITIVES -- up to 5 clean lifecycles per event type\n{'=' * 70}")
    false_positives = 0
    checked = 0
    for event_type in ["session.completed", "task.completed", "followup.required"]:
        clean_candidates = [
            r for r in records
            if r["event_type"] == event_type and r["ref_id"] not in defect_ref_ids
        ][:5]
        for candidate in clean_candidates:
            checked += 1
            finding = investigate_record(candidate, records, retrieve_fn)
            if finding:
                false_positives += 1
                print(f"  [FALSE POSITIVE] event_type={event_type}  ref_id={candidate['ref_id']}")
                print(f"           -> {finding.evidence}")
    print(f"\nFalse positives: {false_positives}/{checked}")

    print(
        f"\n{'=' * 70}\nSUMMARY: System B Tier-2 recall {caught}/{len(tier2_entries)}  |  "
        f"false positives {false_positives}/{checked}\n"
        f"Baseline A (Day 2, measured): Tier-2 recall 0/15, false positives 0\n{'=' * 70}"
    )


if __name__ == "__main__":
    main()