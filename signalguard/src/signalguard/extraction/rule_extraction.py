"""
Claude-based structured rule extraction for SignalGuard.

Converts retrieved documentation chunks into a validated DocumentedRule, or an explicit abstention (INSUFFICIENT_
EVIDENCE / AMBIGUOUS) when the docs don't actually support a rule for the question asked. This is Capability 2
plus the abstention behavior required by the project spec.

The model is forced to respond via tool-use with the ExtractionResult schema (tool_choice pins it to exactly one tool),
so the output is always schema-shaped JSON, never free prose -- schema validity itself becomes a evaluation metric
on top of that structural guarntee.

Chunks are accepted as any object satisfying RetrieveChunk (structural typing, not an import of rag.index.RetrievalResult)
so this module has no dependecy on Chroma -- it only needs four fields, not a vector-DB result type.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from signalguard.llm.reasoner import Reasoner, get_reasoner
from signalguard.schemas.documented_rule import ExtractionResult

MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a documentation-grounded rule extraction system. You will be given one or more excerpts
from internal business documentation, plus a question about whether a specific business rule is documented.

Your job is to determine whether the provided excerpts ACTUALLY document a rule that answers the question, and report
your finding using the record_extraction tool.

Strict grounding requirements:
- Only report a rule if it is explicitly stated in the provided excerpts.
- Never invent, infer, or assume a rule that is not written in the text. 
- If the excerpts discuss the general topic but do not commit to a specific rule (e.g., an open question, an unformalized
policy, or a policy for a different system), you MUST return status="insufficient_evidence" rather than fabricate a
threshold or condition.
- If multiple excerpts appear to conflict or the applicable rule is unclear, return status="ambiguous" and explain why
in `reasoning`.
- Set `source_location` to the exact chunk_id of the excerpt that supports your answer. Never cite a chunk that doesn't
actually contain the rule
"""

class RetrievedChunk(Protocol):
    chunk_id: str
    source_file: str
    heading: str
    text: str

def _build_context(chunks: List[RetrievedChunk]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"[chunk_id: {c.chunk_id}] ({c.source_file} \u2014 {c.heading})\n{c.text}")
    return "\n\n---\n\n".join(parts)

def extract_rule(
        question: str,
        chunks: List[RetrievedChunk],
        reasoner: Optional[Reasoner] = None,
) -> ExtractionResult:
    """
    Ask the configured LLM reasoner whether the given retrieved chunks document a rule answering `question`. 
    Always returns a validated ExtractionResult (DOCUMENTED, INSUFFICIENT_EVIDENCE, or AMBIGUOUS) -- never 
    raises for "no rule found", only for a genuine schema-validation failure (which evaluation counts as a 
    schema-validity defect, not something silently retried here).

    `reasoner` defaults to get_reasoner() (this project's Claude choice, or whatever SIGNALGUARD_LLM_PROVIDER 
    selects) -- pass a FakeReasoner directly in tests to avoid a real API call.
    """
    if reasoner is None:
        reasoner = get_reasoner()

    context = _build_context(chunks)
    user_message = f"Documentation excerpts:\n\n{context}\n\nQuestion: {question}"
    schema = ExtractionResult.model_json_schema()

    raw = reasoner.generate_structured(
        system=_SYSTEM_PROMPT,
        user_message=user_message,
        output_schema=schema,
        tool_name="record_extraction",
        tool_description="Record the rule-extraction finding for this question."        
    )
    return ExtractionResult.model_validate(raw)