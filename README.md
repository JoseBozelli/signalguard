# SignalGuard

SignalGuard is a benchmark-driven system for testing whether documentation-grounded AI can detect data-quality defects in event data that schema validation alone cannot catch.

Structural problems in event data -- a null field, a duplicate ID, an invalid category -- are easy to catch with a schema check. Harder problems are contextual: they only look wrong to someone who already knows a business rule that isn't visible in the data itself (for example, a follow-up event that must occur within a documented SLA window). SignalGuard builds a controlled synthetic benchmark with known injected defects of both kinds, then measures whether a documentation-grounded AI pipeline can detect the harder, rule-dependent class of defect -- and whether it can honestly say "not documented" when it cannot.

## Why SignalGuard?

Most RAG demos show retrieval working on an easy, single-document lookup and stop there. SignalGuard is built the opposite way: the benchmark is designed so retrieval, extraction, and detection can all fail in measurable ways, and every claim about system performance is checked against a hidden answer key rather than eyeballed from a demo. The project is an evaluation exercise first and an AI system second.

## System Overview

```
Synthetic events (clean)
        |
        v  inject known defects (Tier 1: schema-level, Tier 2: rule-level)
Corrupted event batch  +  hidden answer key (never seen by the pipeline)
        |
        +--> Deterministic QC (Baseline A) --> Finding   [IMPLEMENTED]
        |
        +--> Documentation retrieval (RAG)                [IMPLEMENTED]
                    |
                    v
             Structured rule extraction (LLM)             [IMPLEMENTED]
                    |
                    v
             Bounded tool calling                         [IMPLEMENTED]
                    |
                    v
             Finding (System B)                           [IMPLEMENTED]
                    |
                    v
             Evaluation vs. hidden answer key              [IMPLEMENTED -- repeated-run harness, see Current Results]
```

Every stage in the diagram above is built and has run end-to-end against the real corrupted benchmark. What remains is formal, repeated evaluation (Day 5) rather than any missing pipeline stage.

## Benchmark Design

- **Synthetic dataset:** 80 accounts, 821 events, 8 event types (account, session, task, follow-up lifecycles), generated deterministically from a fixed seed.
- **5 documented business rules** (prerequisite, temporal-ordering, and timing-window rules), described in a 4-document corpus that also contains deliberate distractor content and one explicitly *unformalized* policy question -- so retrieval and abstention are both genuinely testable, not trivial.
- **30 injected defects:** 15 Tier 1 (schema-level: duplicate IDs, missing fields, invalid categories -- deterministically detectable) and 15 Tier 2 (rule-level: violate a documented rule, not visible from structure alone).
- **Hidden answer key:** records ground truth for every injected defect, including which documentation chunk and which tool *should* be used to catch it -- kept structurally isolated from anything the retrieval/reasoning code can see.

## Current Results

| System | Tier 1 Recall | Tier 2 Recall | Tier 2 Precision |
|---|---|---|---|
| Deterministic QC (Baseline A) | 100% (15/15) | 0% (0/15) -- by design, it has no rule knowledge | not applicable |
| AI Pipeline (System B) | not applicable -- System B only investigates Tier-2-relevant event types | 100% (15/15), consistent across 3 repeated runs | 100%, consistent across 3 repeated runs |

Baseline A's result is a deliberate contrast, not a shortcoming: it's built to represent "what schema validation alone catches," so System B's Tier-2 numbers are what demonstrate the project's hypothesis -- and across 3 repeated live runs, they do, consistently and without qualification.

Additional measured results (mean across 3 runs, live Claude + Voyage API):
- **Retrieval Recall@3:** 100%
- **Tool-selection accuracy:** 100%
- **Average latency per investigation:** ~8.3 seconds
- **Total cost for 3 full evaluation runs (90 investigations):** $1.57, using Claude Sonnet 4.6 published pricing

### Failure Analysis

An earlier evaluation pass showed two consistent (non-random) anomalies: tool-selection accuracy pinned at exactly 67% every run, and a recurring false positive on one specific clean-control record. Both were root-caused using a dedicated trace-analysis tool (`scripts/analyze_traces.py`) built specifically to break the JSONL execution log down by rule and by outcome -- neither anomaly required touching the detection pipeline itself.

- **Tool-selection mismatch:** the answer key's `RULE_TOOL_MAP` used the singular `check_prerequisite`, written before the real tool existed to name it against; the actual implemented tool has always been `check_prerequisites` (plural). Every R1 case was scored as a mismatch by a one-letter spelling difference between the answer key and the tool registry, not by the model choosing a different (if defensible) tool. An earlier hypothesis in this README -- that the model might be solving the ordering rule via `calculate_interval` instead of `check_event_order` -- was wrong and has been withdrawn; the trace data showed no such substitution ever occurred.
- **Recurring false positive:** traced to one record, `sess_00020`, whose `session.booked` event had been independently mutated by a Tier-1 `invalid_event_type` defect (changed to `session.rescheduled`). This made the record genuinely invisible to the Tier-2 prerequisite check, which was therefore reporting a real (if unintended) defect rather than a spurious one. The evaluation harness's own clean-control filter had a gap: it only excluded ref_ids referenced by a Tier-2 answer-key entry's `affected_ref_id` field, which Tier-1 entries never populate, so a ref_id touched only by a Tier-1 mutation could still be selected as a "clean" control. Fixing the filter to check every answer-key entry's `affected_event_ids` (not just Tier-2's `affected_ref_id`) removed the false positive -- because it correctly was not one.
- **A second bug found during the same fix:** the clean-control sample was intended to be stratified 5 records per investigable event type, but an unstratified list slice silently produced all 15 from `session.completed` alone; `task.completed` and `followup.required` were never actually exercised as clean controls until this was corrected.

Both fixes are in the evaluation harness and the benchmark's cross-tier interaction, not in the detection pipeline itself -- the 100% Tier-2 recall figure was already correct before either fix; only precision and tool-selection accuracy were affected.

## Architecture

- **Schemas (Pydantic):** `Event` (built on a domain-neutral correlation-ID base), `AnswerKeyEntry`, `Finding`, `DocumentedRule`/`ExtractionResult`.
- **Deterministic layer:** synthetic data generator, defect injector, Tier-1-only QC baseline (no rule knowledge, by design).
- **RAG layer:** markdown chunker (one chunk per section), a provider-agnostic `Embedder` interface (Voyage AI in production, a deterministic fake for tests), and a Chroma vector index.
- **LLM layer:** a provider-agnostic `Reasoner` interface (Claude in production, a deterministic fake for tests) forcing schema-shaped output via tool-use, so structured extraction is never free-text parsing.
- **Bounded tools:** three deterministic Python functions (`check_prerequisite`, `check_event_order`, `calculate_interval`) that perform the actual data checks -- the LLM selects which applies and supplies its rule-specific arguments, but never performs the calculation itself.
- **Orchestration:** `investigate_record()` connects retrieval, extraction, and tool selection into one pipeline (System B), producing a `Finding` only when a documented rule was found AND a tool confirmed a violation.
- **Evaluation:** pure, unit-tested metrics functions (precision/recall/F1, Recall@k, tool-selection accuracy) plus a repeated-run evaluation script that produces a durable JSON report.
- **API:** FastAPI service exposing deterministic QC (no external dependency) and the AI-pipeline investigation endpoint (requires Voyage + Claude keys); the Chroma index is built once and cached, not rebuilt per request.
- **Demo:** a Streamlit interface that calls the FastAPI service over HTTP, not by importing pipeline functions directly.
- **Observability:** MLflow run tracking, JSONL execution traces.
- **Not yet built:** Docker, CI.

Provider choice for both embeddings and reasoning is a config value (`SIGNALGUARD_EMBEDDING_PROVIDER`, `SIGNALGUARD_LLM_PROVIDER`), not a hardcoded import -- swapping providers means adding one class, not modifying calling code. Voyage AI and Anthropic Claude are the providers currently implemented; the interfaces (`Embedder`, `Reasoner`) do not assume either one specifically, and a different embedding model or LLM provider could be substituted by implementing the same interface.

## Technology

Python 3.11 - Pydantic v2 - pytest - `uv` (dependency/environment management) - ChromaDB (vector index) - Voyage AI (`voyage-4-lite` embeddings) - Anthropic Claude API (`claude-sonnet-4-6`, structured extraction) - `python-dotenv`

## Repository Structure

```
signalguard/
+-- data/docs_corpus/           # RAG documentation corpus (4 files)
+-- src/signalguard/
|   +-- schemas/                # Event, AnswerKeyEntry, Finding, DocumentedRule
|   +-- data/                   # synthetic generator + defect injector
|   +-- qc/                     # deterministic QC baseline
|   +-- rag/                    # chunking, embeddings, Chroma index
|   +-- llm/                    # provider-agnostic reasoning interface
|   +-- extraction/             # structured rule extraction
|   +-- tools/                  # bounded deterministic tool functions + LLM tool selection
|   +-- pipeline/               # end-to-end orchestration (System B)
|   +-- eval/                   # evaluation metrics (precision/recall/F1, Recall@k, tool-selection accuracy)
|   +-- api/                    # FastAPI service (Baseline QC + AI-pipeline investigate endpoints)
+-- app/                        # Streamlit demo (HTTP client of the API service)
+-- .streamlit/                 # theme configuration
+-- scripts/                    # smoke tests, evaluation runner, trace analysis (live API where noted, not pytest)
+-- tests/
+-- eval_report.json            # output of the most recent formal evaluation run
```

## Running Locally

Environment setup:
```bash
uv sync
```

Copy `.secrets.example` to `.secrets` and populate:
```
VOYAGE_API_KEY=
ANTHROPIC_API_KEY=
```
These correspond to the embedding and reasoning providers currently implemented (Voyage AI and Anthropic Claude). Different providers could be substituted by implementing the `Embedder` or `Reasoner` interface and setting `SIGNALGUARD_EMBEDDING_PROVIDER` / `SIGNALGUARD_LLM_PROVIDER` accordingly.

Automated test suite (no API keys required -- tests use deterministic fakes for both embedding and reasoning):
```bash
uv run pytest tests/ -v
```

Live extraction smoke test (requires both API keys, makes real billed calls):
```bash
uv run python scripts/smoke_test_extraction.py
```

Live end-to-end pipeline smoke test (System B -- requires both API keys, ~30 pipeline runs, real billed calls):
```bash
uv run python scripts/smoke_test_pipeline.py
```

Formal evaluation (3 repeated runs, ~90 pipeline runs, real billed calls -- approximately $0.54/run on Claude Sonnet 4.6 pricing at this benchmark's scale):
```bash
uv run python scripts/run_evaluation.py
```
Writes a full per-run report to `eval_report.json` and per-investigation traces to `traces/evaluation_traces.jsonl` at the repository root.

Trace analysis (local file only, no API calls, free to re-run):
```bash
uv run python scripts/analyze_traces.py
```
Reports tool-selection agreement per rule and false positives on clean controls -- this is the tool that diagnosed both anomalies described in Failure Analysis above.

API service (Baseline QC works with no external API; the investigate endpoint requires both keys):
```bash
uv add fastapi uvicorn httpx
uv run uvicorn signalguard.api.app:app --reload
```
Interactive API docs at `http://127.0.0.1:8000/docs`.

Demo interface (requires the API service running in a separate terminal):
```bash
uv add streamlit requests
uv run streamlit run app/streamlit_app.py
```
The Baseline QC tab works immediately with no external API. The Investigate tab makes a live, billed Claude + Voyage call per record and requires both keys configured in `.secrets` -- without them, that tab returns an error rather than a result, which is expected: cloning this repository provides the code, not working API access. Each person running it supplies their own keys and bears their own API cost.

## Testing

```bash
uv run pytest tests/ -v
```
146 tests passing as of this writing. The suite never depends on a live API call -- both `Embedder` and `Reasoner` have deterministic fake implementations used throughout the test suite, including for the API layer (FastAPI's dependency injection is overridden with fakes in tests).

## Project Status

**Completed:** synthetic data generation, corruption benchmark with hidden answer key, deterministic QC baseline (measured), RAG corpus + chunking + retrieval, provider-agnostic embedding/reasoning interfaces, structured extraction with verified abstention behavior, bounded tool functions, full end-to-end orchestration (System B), observability (JSONL execution traces + MLflow run tracking), a repeated-run evaluation harness (3 runs, real cost/latency tracking), a FastAPI service (deterministic QC + AI-pipeline investigation endpoints), and a Streamlit demo interface. Measured result: 100% Tier-2 recall, precision, retrieval, and tool-selection accuracy, consistent across all 3 evaluation runs, against Baseline A's measured 0% Tier-2 recall. Two earlier anomalies in that evaluation were root-caused and fixed using a dedicated trace-analysis tool -- see Failure Analysis above.

**In progress:** none actively mid-build at this checkpoint.

**Planned:** Docker, CI, architecture diagram.

## Engineering Decisions

- The deterministic baseline is deliberately kept ignorant of documented rules, so its comparison against the AI pipeline is fair rather than pre-loaded.
- The RAG corpus mixes rules, distractors, and one genuinely unformalized policy in the same documents, so retrieval and abstention are both falsifiable, not assumed.
- Embedding and reasoning providers sit behind interfaces with deterministic fakes, so the test suite has zero cost and zero network dependency.
- The hidden answer key (including retrieval and tool-selection gold labels) was designed before any detection code was written, and is structurally isolated from the reasoning path.
- The Streamlit demo calls the FastAPI service over HTTP rather than importing pipeline functions directly, so the demo genuinely exercises the API layer rather than bypassing it.
- Anomalous evaluation results (a pinned tool-selection rate, a recurring false positive) were root-caused with a dedicated trace-analysis tool rather than accepted as model unreliability or patched by re-running -- both turned out to be bugs in the evaluation harness itself, not the detection pipeline.

## Roadmap

Remaining work: repository polish (Docker, CI, architecture diagram) and the R3/R4 benchmark coverage gap.

## Limitations

- All data is synthetic; no real event stream or production data has been used.
- The benchmark is intentionally small (30 defects, 5 rules) -- results should be read as a controlled proof of method, not a large-scale accuracy claim.
- The 100% System B Tier-2 recall, precision, retrieval, and tool-selection figures are repeated-run results (3 independent runs, identical outcome each time) against a real hidden benchmark of 15 defects and 15 clean controls -- see Current Results and Failure Analysis for how two earlier anomalies were diagnosed and resolved.
- Two of the five documented rules (R3, R4) currently have zero injected benchmark instances exercising them.
- This is a portfolio project; no production deployment, real users, or commercial use exists.

## License

MIT License. See `LICENSE`.