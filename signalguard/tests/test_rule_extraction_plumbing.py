import unittest

from signalguard.extraction.rule_extraction import extract_rule
from signalguard.llm.reasoner import FakeReasoner
from signalguard.schemas.documented_rule import ExtractionStatus

class TestExtractRulePlumbing(unittest.TestCase):
    """
    Uses FakeReasoner to test extract_rule()'s plumbing -- schema construction, prompt assembly, and result parsing/
    validation -- with zero network calls. This does NOT test whether Claude actually respects grounding/abstention
    instructions; that's what scripts/smoke_test_extraction.py verifies against the real API.
    """

    def test_documented_case_parses_correctly(self):
        canned = {
            "status": "documented",
            "rule": {
                "rule_id": "r-test",
                "rule_type": "timing_window",
                "relevant_events": ["session.no_show", "followup.required"],
                "condition": "Follow-up required within 7 days of a no-show.",
                "source_document": "sla-and-timing-policies.md",
                "source_location": "sla-and-timing-policies.md::follow-up-response-window-after-a-missed-session",
                "confidence": "high",
                "requires_tool": "calculate_interval",
            },
            "reasoning": "Explicitly documented in the SLA section."
        }
        result = extract_rule("test question", [], reasoner=FakeReasoner(canned))

        self.assertEqual(result.status, ExtractionStatus.DOCUMENTED)
        self.assertIsNotNone(result.rule)
        self.assertEqual(result.rule.requires_tool, "calculate_interval")

    def test_insufficient_evidence_case_parses_correctly(self):
        canned = {
            "status": "insufficient_evidence",
            "rule": None,
            "reasoning": "The docs explicitly say this has not been formalized."
        }
        result = extract_rule("test question", [], reasoner=FakeReasoner(canned))

        self.assertEqual(result.status, ExtractionStatus.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(result.rule)

    def test_malformed_canned_response_raises_validation_error(self):
        # A response missing required fields should fail Pydantic validation rather than being silently accepted --
        # this is exactly the schema-validity failure mode evaluation is meant to catch.
        canned = {"status": "documented"}   # missing required "reasoning"
        with self.assertRaises(Exception):
            extract_rule("test question", [], reasoner=FakeReasoner(canned))

if __name__ == "__main__":
    unittest.main()