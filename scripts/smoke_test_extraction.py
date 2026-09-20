"""
Manual smoke test for Capability 2: documentation-grounded structured extraction. NOT a pytest test --
this makes real, billed calls to both Voyage AI (embeddings) and the Claude API, and LLM output is 
non-deterministic, so it doesn't belong in an automated test suite.

Run it by hand and read the output:
    uv run python scripts/smoke_test_extraction.py

It covers exactly the two cases that matter most for this project:
    1. A DOCUMENTED case -- should ground correctly in the SLA section
    2. An INSUFFICIENT_EVIDENCE case -- the deliberately unformalized "how long can booking take" question from the
    doc corpus
"""

from pathlib import Path

from signalguard.extraction.rule_extraction import extract_rule
from signalguard.rag.chunking import chunk_corpus
from signalguard.rag.embeddings import get_embedder
from signalguard.rag.index import build_index, retrieve

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"

def run_case(label: str, question: str, embedder, collection, expected_status: str) -> bool:
    print(f"\n{'=' * 70}\n{label}\nQuestion: {question}\n{'=' * 70}")
    chunks = retrieve(collection, question, embedder, k=3)
    print("Retrieve chunks:")
    for c in chunks:
        print(f" - {c.chunk_id} (score={c.score:.3f})")

    result = extract_rule(question, chunks)
    print(f"\nStatus: {result.status.value} (expected: {expected_status})")
    print(f"Reasoning: {result.reasoning}")
    if result.rule:
        print(f"Rule: {result.rule.condition}")
        print(f" source_location: {result.rule.source_location}")
        print(f" requires_tool: {result.rule.requires_tool}")

    passed = result.status.value == expected_status
    print("PASS" if passed else "MISMATCH -- inspect manually")
    return passed

def main():
    embedder = get_embedder()   # defaults to Voyage: override via SIGNALGUARD_EMBEDDING_PROVIDER
    collection = build_index(DOCS_DIR, embedder)

    results = []
    results.append(
        run_case(
            "Case 1: DOCUMENTED (should ground in the SLA section)",
            "How many days after a session no-show must a follow-up be required?",
            embedder,
            collection,
            expected_status="documented"
        )
    )
    results.append(
        run_case(
            "Case 2: INSUFFICIENT_EVIDENCE (deliberately unformalized policy)",
            "What is the maximum allowed interval between a session being booked and that session being completed?",
            embedder,
            collection,
            expected_status="insufficient_evidence"
        )
    )

    print(f"\n{'=' * 70}\n{sum(results)}/{len(results)} cases matched expected status\n{'=' * 70}")

if __name__ == "__main__":
    main()