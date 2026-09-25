"""
FastAPI service exposing SignalGuard's core capabilities (Capability 5).

This first version exposes only the deterministic QC baseline -- no
external API dependency, always available, always fast. The
documentation-grounded AI pipeline endpoint (System B) is added
separately, once this foundation is confirmed working, since it needs a
live Chroma index and configured API keys and is a meaningfully larger
piece of surface area to get right in one step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from signalguard.pipeline.orchestrator import investigate_record as _investigate_record
from signalguard.qc.deterministic import run_baseline_qc
from signalguard.rag.embeddings import get_embedder
from signalguard.rag.index import build_index, retrieve
from signalguard.schemas.finding import Finding

app = FastAPI(
    title="SignalGuard API",
    description="Documentation-grounded data-quality detection for event streams.",
    version="0.1.0",
)


class BaselineQCRequest(BaseModel):
    records: List[Dict[str, Any]]


class BaselineQCResponse(BaseModel):
    findings: List[Finding]

class InvestigateRequest(BaseModel):
    candidate: Dict[str, Any]
    all_records: List[Dict[str, Any]]

class InvestigateResponse(BaseModel):
    finding: Optional[Finding]


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/qc/baseline", response_model=BaselineQCResponse)
def qc_baseline(request: BaselineQCRequest) -> BaselineQCResponse:
    """
    Deterministic Tier-1 QC (Baseline A). No LLM, no external API,
    always available -- see qc/deterministic.py for what it checks.
    """
    findings = run_baseline_qc(request.records)
    return BaselineQCResponse(findings=findings)

_pipeline_cache: Dict[str, Any] = {}

def _build_investigate_fn():
    docs_dir = Path(__file__).resolve().parents[3] / "data" / "docs_corpus"
    embedder = get_embedder()
    collection = build_index(docs_dir, embedder)

    def _investigate(candidate: Dict[str, Any], all_records: List[Dict[str, Any]]) -> Optional[Finding]:
        return _investigate_record(candidate, all_records, lambda q: retrieve(collection, q, embedder, k=3))

    return _investigate

def get_investigate_fn():
    """
    FastAPI dependency provider for the System B pipeline. The Chroma index is built once (module-level cache)
    rather than per-request -- re-embedding the corpus on every call would be needlessly slow and costly.
    Overriden in tests via app.dependency_overrides so the test suite never needs live API keys for this endpoint.
    """
    if "investigate" not in _pipeline_cache:
        _pipeline_cache["investigate"] = _build_investigate_fn()
    return _pipeline_cache["investigate"]

@app.post("/qc/investigate", response_model=InvestigateResponse)
def qc_investigate(
    request: InvestigateRequest,
    investigate_fn=Depends(get_investigate_fn),
) -> InvestigateResponse:
    """
    Documentation-grounded investigation of a single record (System B). Requires ANTHROPIC_API_KEY
    and VOYAGE_API_KEY to be configured.
    """
    try:
        finding = investigate_fn(request.candidate, request.all_records)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline execution failed: {exc}") from exc
    return InvestigateResponse(finding=finding)