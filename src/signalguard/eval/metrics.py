"""
Evaluation metrics for SignalGuard.

These functions are pure and deterministic -- they score already-produced Findings/results agains the hidden
answer key. None of them call an LLM or embedding API; that happens only in the runner script (scripts/
run_evaluation.py). Keeping metrics computation separate and pure means it is fully unit-testable, and
reusable for scoring any future run's output without re-executing the pipeline.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel

from signalguard.schemas.answer_key import AnswerKeyEntry
from signalguard.schemas.finding import Finding

class DetectionMetrics(BaseModel):
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1:float

def _finding_matches_entry(finding: Finding, entry: AnswerKeyEntry) -> bool:
    """
    A Finding is a match for an answer-key entry when they share at least one affected_event_id. This mirrors the
    matching rules already used in Baseline A's own evaluatiion test, kept consistent here rather than redefined.
    """
    return bool(set(finding.affected_event_ids) & set(entry.affected_event_ids))

def compute_detection_metrics(
        findings: Sequence[Finding],
        answer_key: Sequence[AnswerKeyEntry],
        tier: Optional[str] = None,
) -> DetectionMetrics:
    """
    Computes precision/recall/F1 for a set of Findings against the hidden answer key. If `tier` is given ("tier1"
    or "tier2"), only entries and findings of that tier are considered -- this is how Baseline A's Tier-1-only and
    System B's Tier-2-only evaluations stay separately meaningful rather than diluting each other.

    A Finding that matches an answer-key entry already credited to an earlier Finding counts as a false positive,
    not a second true positive -- duplicate reports of the same real defect do not inflate recall.
    """
    relevant_entries = [e for e in answer_key if tier is None or e.tier == tier]
    relevant_findings = [f for f in findings if tier is None or f.tier == tier]

    matched_entry_ids: Set[str] = set()
    true_positives = 0
    false_positives = 0

    for finding in relevant_findings:
        match = next((e for e in relevant_entries if _finding_matches_entry(finding, e)), None)

        if match is not None and match.defect_id not in matched_entry_ids:
            matched_entry_ids.add(match.defect_id)
            true_positives += 1
        else:
            false_positives += 1

    false_negatives = len(relevant_entries) - len(matched_entry_ids)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return DetectionMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1
    )

def compute_retrieval_hit(retrieved_chunk_ids: Iterable[str], gold_chunk_ids: Iterable[str]) -> bool:
    """Recall@k for a single query: True if any gold chunk was retrieved."""
    return bool(set(retrieved_chunk_ids) & set(gold_chunk_ids))

def compute_retrieval_recall_at_k(hits: Sequence[bool]) -> float:
    """Aggregate Recall@k across multiple queries: the fraction that hit."""
    if not hits:
        return 0.0
    return sum(1 for h in hits if h) / len(hits)

def compute_tool_selection_accuracy(selections: Sequence[Tuple[str, str]]) -> float:
    """
    Given (selected_tool_name, expected_tool_name) pairs, returns the fraction where the model's independent 
    selection matched the hidden answer key's expected_tool.
    """
    if not selections:
        return 0.0
    correct = sum(1 for selected, expected in selections if selected == expected)
    return correct / len(selections)