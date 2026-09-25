import unittest
from dataclasses import dataclass

from signalguard.llm.reasoner import FakeReasoner
from signalguard.pipeline.orchestrator import (
    investigate_record, 
    investigate_record_with_trace, 
    pick_investigable_candidate
)

@dataclass
class FakeChunk:
    chunk_id: str
    source_file: str
    heading: str
    text: str


_DUMMY_CHUNKS = [FakeChunk("doc.md::h", "doc.md", "h", "text")]

_DOCUMENTED_RULE = {
    "status": "documented",
    "rule": {
        "rule_id": "r1",
        "rule_type": "prerequisite",
        "relevant_events": ["session.booked", "session.completed"],
        "condition": "completion requires booking",
        "source_document": "d.md",
        "source_location": "d.md::h",
        "confidence": "high",
    },
    "reasoning": "documented",
}

_PREREQUISITE_TOOL_CALL = {
    "tool_name": "check_prerequisites",
    "tool_input": {"prerequisite_event_type": "session.booked", "dependent_event_type": "session.completed"},
}


class TestInvestigateRecord(unittest.TestCase):
    def test_unrecognized_event_type_returns_none_without_retrieving(self):
        calls = []

        def retrieve_fn(q):
            calls.append(q)
            return _DUMMY_CHUNKS

        record = {"event_type": "account.created", "ref_id": None, "event_id": "e1", "account_id": "a1"}
        result = investigate_record(record, [], retrieve_fn, reasoner=FakeReasoner(canned_response={}))

        self.assertIsNone(result)
        self.assertEqual(calls, [])  # retrieval never even attempted

    def test_insufficient_evidence_returns_none(self):
        reasoner = FakeReasoner(
            canned_response={"status": "insufficient_evidence", "rule": None, "reasoning": "not documented"},
        )
        record = {"event_type": "session.completed", "ref_id": "ref1", "event_id": "e1", "account_id": "a1"}
        result = investigate_record(record, [], lambda q: _DUMMY_CHUNKS, reasoner=reasoner)
        self.assertIsNone(result)

    def test_documented_but_no_violation_returns_none(self):
        reasoner = FakeReasoner(canned_response=_DOCUMENTED_RULE, canned_tool_call=_PREREQUISITE_TOOL_CALL)
        records = [
            {"ref_id": "ref1", "event_type": "session.booked", "timestamp": "2026-01-01T00:00:00"},
            {
                "ref_id": "ref1",
                "event_type": "session.completed",
                "timestamp": "2026-01-02T00:00:00",
                "event_id": "e1",
                "account_id": "a1",
            },
        ]
        candidate = records[1]
        result = investigate_record(candidate, records, lambda q: _DUMMY_CHUNKS, reasoner=reasoner)
        self.assertIsNone(result)  # booked IS present -> no violation

    def test_documented_and_violated_returns_finding(self):
        reasoner = FakeReasoner(canned_response=_DOCUMENTED_RULE, canned_tool_call=_PREREQUISITE_TOOL_CALL)
        records = [
            {
                "ref_id": "ref1",
                "event_type": "session.completed",
                "timestamp": "2026-01-02T00:00:00",
                "event_id": "e1",
                "account_id": "a1",
            },
        ]
        candidate = records[0]
        result = investigate_record(candidate, records, lambda q: _DUMMY_CHUNKS, reasoner=reasoner)

        self.assertIsNotNone(result)
        self.assertEqual(result.source, "ai_pipeline")
        self.assertEqual(result.tier, "tier2")
        self.assertEqual(result.reasoning_category, "documented_rule")
        self.assertEqual(result.rule_id, "r1")
        self.assertEqual(result.affected_ref_id, "ref1")
        self.assertEqual(result.confidence, "high")

class TestInvestigateRecordWithTrace(unittest.TestCase):
    def test_trace_captures_every_stage_on_a_violation(self):
        reasoner = FakeReasoner(canned_response=_DOCUMENTED_RULE, canned_tool_call=_PREREQUISITE_TOOL_CALL)
        records = [
            {
                "ref_id": "ref1",
                "event_type": "session.completed",
                "timestamp": "2026-01-02T00:00:00",
                "event_id": "e1",
                "account_id": "a1"
            }
        ]
        trace = investigate_record_with_trace(records[0], records, lambda q: _DUMMY_CHUNKS, reasoner=reasoner)

        self.assertEqual(trace.event_type, "session.completed")
        self.assertIsNotNone(trace.question)
        self.assertEqual(trace.retrieved_chunk_ids, ["doc.md::h"])
        self.assertEqual(trace.extraction_status, "documented")
        self.assertEqual(trace.extracted_rule_id, "r1")
        self.assertEqual(trace.selected_tool, "check_prerequisites")
        self.assertTrue(trace.tool_violated)
        self.assertIsNotNone(trace.finding)

    def test_trace_stops_early_for_unrecognized_event_type(self):
        record = {"event_type": "account.created", "ref_id": None, "event_id": "e1", "account_id": "a1"}
        trace = investigate_record_with_trace(
            record, [], lambda q: _DUMMY_CHUNKS, reasoner=FakeReasoner(canned_response={})
        )
        self.assertIsNone(trace.question)
        self.assertEqual(trace.retrieved_chunk_ids, [])
        self.assertIsNone(trace.extraction_status)
        self.assertIsNone(trace.finding)

    def test_trace_captures_abstention_without_reaching_tool_selection(self):
        reasoner = FakeReasoner(
            canned_response={"status": "insufficient_evidence", "rule": None, "reasoning": "not documented"}
        )
        record = {"event_type": "session.completed", "ref_id": "ref1", "event_id": "e1", "account_id": "a1"}
        trace = investigate_record_with_trace(record, [], lambda q: _DUMMY_CHUNKS, reasoner=reasoner)

        self.assertEqual(trace.extraction_status, "insufficient_evidence")
        self.assertIsNone(trace.selected_tool)  # never reached tool selection
        self.assertIsNone(trace.finding)

class TestPickInvestigableCandidate(unittest.TestCase):
    def test_picks_the_investigable_record_among_multiple_ids(self):
        records_by_id = {
            "req1": {"event_id": "req1", "event_type": "task.required"},
            "comp1": {"event_id": "comp1", "event_type": "task.completed"}
        }
        # task.required is NOT investigable, task.completed IS -- order in the list deliberately puts the 
        # non-investigable one first, as the real bad_ordering/R2 answer-key entries do.
        picked = pick_investigable_candidate(["req1", "comp1"], records_by_id)
        self.assertEqual(picked["event_id"], "comp1")

    def test_falls_back_to_first_id_when_none_investigable(self):
        records_by_id = {"a1": {"event_id": "a1", "event_type": "account.created"}}
        picked = pick_investigable_candidate(["a1"], records_by_id)
        self.assertEqual(picked["event_id"], "a1")


if __name__ == "__main__":
    unittest.main()