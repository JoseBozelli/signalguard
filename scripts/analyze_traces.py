"""
Print a readable failure-analysis report from the evaluation traces.

Reads traces/evaluation_traces.jsonl (written by scripts/run_evaluation.py)
and reports tool-selection agreement per rule, false positives on clean
controls, and extraction-status counts. No API calls -- reads a local
file only, so it is free to run as often as needed.

Usage:
    uv run python scripts/analyze_traces.py
"""

import sys
from pathlib import Path

from signalguard.eval.trace_analysis import format_report, summarize_traces
from signalguard.observability.tracing import JSONLTracer

DEFAULT_TRACES_PATH = Path(__file__).resolve().parent.parent / "traces" / "evaluation_traces.jsonl"


def main(traces_path: Path = DEFAULT_TRACES_PATH) -> None:
    records = JSONLTracer(traces_path).read_all()
    if not records:
        print(f"No trace records found at {traces_path}. Run scripts/run_evaluation.py first.")
        return
    print(format_report(summarize_traces(records)))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACES_PATH)