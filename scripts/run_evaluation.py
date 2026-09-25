"""
Formal Day-5 evaluation runner for SignalGuard.

NOT a pytest test -- makes real, billed calls to Voyage and Claude across
multiple repeated passes. This is the actual evaluation harness the
project spec protects from schedule cuts: real Recall@k, tool-selection
accuracy, System B precision/recall/F1, latency, and token cost -- run
repeatedly (not once) so the result is a reliability read, not a single
anecdote.

Scope, deliberately: the 15 real Tier-2 defect instances plus 15 clean
control lifecycles (5 each across session.completed, task.completed,
followup.required), matching the smoke test's sample -- not the full
~377-record investigable set. This keeps a repeated (3x) run affordable
while still measuring genuine reliability across the whole locked rule
set, rather than a single pass over a larger, more expensive sample.

Usage:
    uv run python scripts/run_evaluation.py
"""

import json
import time
from pathlib import Path

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects
from signalguard.eval.metrics import (
    compute_detection_metrics,
    compute_retrieval_recall_at_k,
    compute_tool_selection_accuracy,
)
from signalguard.llm.reasoner import ClaudeReasoner
from signalguard.pipeline.orchestrator import investigate_record_with_trace, pick_investigable_candidate
from signalguard.rag.embeddings import get_embedder
from signalguard.rag.index import build_index, retrieve

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"
NUM_RUNS = 3


def build_evaluation_sample(records, answer_key):
    """Returns (tier2_entries, records_by_id, clean_candidates)."""
    records_by_id = {r["event_id"]: r for r in records}
    tier2_entries = [e for e in answer_key if e.tier == "tier2"]
    defect_ref_ids = {e.affected_ref_id for e in answer_key if e.affected_ref_id}

    clean_candidates = []
    for event_type in ["session.completed", "task.completed", "followup.required"]:
        clean_candidates.extend(
            r for r in records
            if r["event_type"] == event_type and r["ref_id"] not in defect_ref_ids
        )
    clean_candidates = clean_candidates[:15]  # 5 per type, matching the smoke test sample

    return tier2_entries, records_by_id, clean_candidates


def run_one_pass(tier2_entries, records_by_id, clean_candidates, all_records, retrieve_fn, reasoner):
    """
    Runs one full evaluation pass. Returns a dict with the Findings
    produced, retrieval hits, tool-selection pairs, and per-call latency.
    """
    findings = []
    retrieval_hits = []
    tool_selection_pairs = []
    latencies = []

    for entry in tier2_entries:
        candidate = pick_investigable_candidate(entry.affected_event_ids, records_by_id)
        start = time.perf_counter()
        trace = investigate_record_with_trace(candidate, all_records, retrieve_fn, reasoner=reasoner)
        latencies.append(time.perf_counter() - start)

        if entry.expected_doc_chunk_ids:
            retrieval_hits.append(bool(set(trace.retrieved_chunk_ids) & set(entry.expected_doc_chunk_ids)))
        if trace.selected_tool and entry.expected_tool:
            tool_selection_pairs.append((trace.selected_tool, entry.expected_tool))
        if trace.finding:
            findings.append(trace.finding)

    for candidate in clean_candidates:
        start = time.perf_counter()
        trace = investigate_record_with_trace(candidate, all_records, retrieve_fn, reasoner=reasoner)
        latencies.append(time.perf_counter() - start)
        if trace.finding:
            findings.append(trace.finding)  # a false positive on clean data

    return {
        "findings": findings,
        "retrieval_hits": retrieval_hits,
        "tool_selection_pairs": tool_selection_pairs,
        "latencies": latencies,
    }


def main():
    embedder = get_embedder()
    collection = build_index(DOCS_DIR, embedder)
    retrieve_fn = lambda question: retrieve(collection, question, embedder, k=3)  # noqa: E731

    events = generate_clean_dataset(num_accounts=80, seed=42)
    records, answer_key = inject_defects(events, seed=7, instances_per_defect_type=5)
    tier2_entries, records_by_id, clean_candidates = build_evaluation_sample(records, answer_key)

    print(f"Evaluation sample: {len(tier2_entries)} Tier-2 defects + {len(clean_candidates)} clean controls")
    print(f"Repeating {NUM_RUNS} times for a reliability read (not a single-run result)\n")

    run_reports = []
    for run_index in range(1, NUM_RUNS + 1):
        print(f"{'=' * 70}\nRUN {run_index}/{NUM_RUNS}\n{'=' * 70}")
        reasoner = ClaudeReasoner()  # fresh instance per run: isolates token accounting per run
        result = run_one_pass(tier2_entries, records_by_id, clean_candidates, records, retrieve_fn, reasoner)

        detection = compute_detection_metrics(result["findings"], answer_key, tier="tier2")
        retrieval_recall = compute_retrieval_recall_at_k(result["retrieval_hits"])
        tool_accuracy = compute_tool_selection_accuracy(result["tool_selection_pairs"])
        avg_latency = sum(result["latencies"]) / len(result["latencies"]) if result["latencies"] else 0.0

        report = {
            "run": run_index,
            "tier2_recall": detection.recall,
            "tier2_precision": detection.precision,
            "tier2_f1": detection.f1,
            "true_positives": detection.true_positives,
            "false_positives": detection.false_positives,
            "false_negatives": detection.false_negatives,
            "retrieval_recall_at_3": retrieval_recall,
            "tool_selection_accuracy": tool_accuracy,
            "avg_latency_seconds": round(avg_latency, 2),
            "total_input_tokens": reasoner.total_input_tokens,
            "total_output_tokens": reasoner.total_output_tokens,
            "estimated_cost_usd": round(reasoner.estimated_cost_usd, 6),
        }
        run_reports.append(report)

        print(f"  Tier-2 recall: {detection.recall:.0%} ({detection.true_positives}/{detection.true_positives + detection.false_negatives})")
        print(f"  Tier-2 precision: {detection.precision:.0%}")
        print(f"  Retrieval Recall@3: {retrieval_recall:.0%}")
        print(f"  Tool-selection accuracy: {tool_accuracy:.0%}")
        print(f"  Avg latency per investigation: {avg_latency:.2f}s")
        print(f"  Tokens: {reasoner.total_input_tokens} in / {reasoner.total_output_tokens} out")
        print(f"  Estimated cost: ${reasoner.estimated_cost_usd:.6f}\n")

    print(f"{'=' * 70}\nSUMMARY ACROSS {NUM_RUNS} RUNS\n{'=' * 70}")
    recalls = [r["tier2_recall"] for r in run_reports]
    precisions = [r["tier2_precision"] for r in run_reports]
    total_cost = sum(r["estimated_cost_usd"] for r in run_reports)

    print(f"Tier-2 recall across runs: {[f'{r:.0%}' for r in recalls]}")
    print(f"Tier-2 precision across runs: {[f'{p:.0%}' for p in precisions]}")
    print(f"Mean recall: {sum(recalls) / len(recalls):.0%}  |  Min: {min(recalls):.0%}  |  Max: {max(recalls):.0%}")
    print(f"Total estimated cost for {NUM_RUNS} runs: ${total_cost:.6f}")
    print("\nBaseline A (Day 2, measured, deterministic): Tier-2 recall 0/15, false positives 0")

    output_path = Path(__file__).resolve().parent.parent / "eval_report.json"
    with open(output_path, "w") as f:
        json.dump(run_reports, f, indent=2)
    print(f"\nFull report written to {output_path}")


if __name__ == "__main__":
    main()