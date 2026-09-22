import unittest
from dataclasses import dataclass

from signalguard.llm.reasoner import FakeReasoner
from signalguard.pipeline.orchestrator import investigate_record


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


if __name__ == "__main__":
    unittest.main()