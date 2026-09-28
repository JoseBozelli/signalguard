"""
Trace analysis for SignalGuard.

Pure functions over the JSONL trace records written by
observability.tracing.JSONLTracer. They turn the raw per-investigation
log into the specific failure-analysis views the evaluation needs:
tool-selection agreement per rule, false positives on clean controls,
and extraction-status counts. No API calls and no file I/O in the core
functions, so they are fully testable with synthetic records.

Motivating case: a tool-selection accuracy that stayed pinned at exactly
67% across runs looked like a model-behavior effect, but the per-rule
breakdown here shows it as a naming mismatch between the tool registry
and the answer key -- visible only once each investigation was logged
individually.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List


def summarize_traces(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    seeded = [r for r in records if r.get("candidate_kind") == "seeded_defect"]
    clean = [r for r in records if r.get("candidate_kind") == "clean_control"]

    per_rule: Dict[Any, Dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "matches": 0, "expected_tool": None, "selected_tools": Counter()}
    )
    for record in seeded:
        entry = per_rule[record.get("rule_id")]
        entry["total"] += 1
        entry["expected_tool"] = record.get("expected_tool")
        selected = record.get("selected_tool")
        entry["selected_tools"][selected] += 1
        if selected is not None and selected == record.get("expected_tool"):
            entry["matches"] += 1

    tool_agreement = {
        rule: {
            "total": info["total"],
            "matches": info["matches"],
            "expected_tool": info["expected_tool"],
            "selected_tools": dict(info["selected_tools"]),
        }
        for rule, info in per_rule.items()
    }

    false_positives = [
        {
            "run_id": record.get("run_id"),
            "event_type": record.get("event_type"),
            "ref_id": record.get("ref_id"),
            "selected_tool": record.get("selected_tool"),
            "evidence": (record.get("finding") or {}).get("evidence"),
        }
        for record in clean
        if record.get("finding")
    ]

    return {
        "total_records": len(records),
        "seeded_defect_records": len(seeded),
        "clean_control_records": len(clean),
        "tool_agreement_by_rule": tool_agreement,
        "false_positives": false_positives,
        "extraction_status_counts": dict(Counter(r.get("extraction_status") for r in records)),
    }


def format_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"Trace records: {summary['total_records']} "
        f"({summary['seeded_defect_records']} seeded defects, "
        f"{summary['clean_control_records']} clean controls)"
    )
    lines.append("")
    lines.append("Tool selection vs. answer key, by rule:")
    for rule, info in sorted(summary["tool_agreement_by_rule"].items(), key=lambda kv: str(kv[0])):
        flag = "" if info["matches"] == info["total"] else "   <-- MISMATCH"
        lines.append(
            f"  {rule}: {info['matches']}/{info['total']} match "
            f"(expected '{info['expected_tool']}'){flag}"
        )
        lines.append(f"      selected: {info['selected_tools']}")
    lines.append("")

    false_positives = summary["false_positives"]
    lines.append(f"False positives on clean controls: {len(false_positives)}")
    for fp in false_positives:
        lines.append(f"  run {fp['run_id']}: {fp['event_type']} ref_id={fp['ref_id']} tool={fp['selected_tool']}")
        lines.append(f"      {fp['evidence']}")
    lines.append("")
    lines.append(f"Extraction status counts: {summary['extraction_status_counts']}")
    return "\n".join(lines)