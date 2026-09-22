import unittest

from signalguard.llm.reasoner import FakeReasoner
from signalguard.schemas.documented_rule import DocumentedRule, RuleType
from signalguard.tools.tool_selection import select_and_execute_tool

def _make_rule(**overrides) -> DocumentedRule:
    defaults = dict(
        rule_id = "r-test",
        rule_type = RuleType.PREREQUISITE,
        relevant_events=["session.booked", "session.completed"],
        condition = "A session.completed event requires a preceding session.booked event.",
        source_document = "event-lifecycle-rules.md",
        source_location = "event-lifecycle-rules.md::sessiong-booking-and-completion",
        confidence="high",
    )
    defaults.update(overrides)
    return DocumentedRule(**defaults)

class TestSelectAndExecuteTool(unittest.TestCase):
    """
    Uses FakeResoner's canned tool selection to test the merge logic: does select_and_execute_tool correctly combine
    the model's rule-interpretation arguments with the caller-supplied ref_id/records, and correctly dispatch to the
    matching Python functon -- with zero network calls. Real tool-SELECTION quality (did the model choose correctly
    given only the rule) is a live-API smoke test, not this.
    """

    def test_check_prerequisites_dispatch(self):
        records =[
            {"ref_id": "ref1", "event_type": "session.completed", "timestamp": "2026-01-05T00:00:00"},
        ]
        reasoner = FakeReasoner(
            canned_response={},
            canned_tool_call={
                "tool_name": "check_prerequisites",
                "tool_input": {
                    "prerequisite_event_type": "session.booked",
                    "dependent_event_type": "session.completed",
                },
            },
        )
        tool_name, result = select_and_execute_tool(_make_rule(), "ref1", records, reasoner=reasoner)

        self.assertEqual(tool_name, "check_prerequisites")
        self.assertTrue(result.violated)    # booked is missing from records

    def test_check_event_order_dispatch(self):
        records =[
             {"ref_id": "ref1", "event_type": "task.required", "timestamp": "2026-01-05T00:00:00"},
             {"ref_id": "ref1", "event_type": "task.completed", "timestamp": "2026-01-01T00:00:00"},
        ]
        reasoner = FakeReasoner(
                canned_response={},
                canned_tool_call={
                    "tool_name": "check_event_order",
                    "tool_input": {
                        "first_event_type": "task.required",
                        "second_event_type": "task.completed",
                },
            },
        )
        tool_name, result = select_and_execute_tool(_make_rule(), "ref1", records, reasoner=reasoner)
        
        self.assertEqual(tool_name, "check_event_order")
        self.assertTrue(result.violated)    # required is after completed

    def test_calculate_interval_dispatch_requires_related_ref_id(self):
        records = [
            {"ref_id": "sess1", "event_type": "session.no_show", "timestamp": "2026-01-01T00:00:00"},
            {"ref_id": "fu1", "event_type": "followup.required", "timestamp": "2026-01-15T00:00:00"},
        ]
        reasoner = FakeReasoner(
            canned_response={},
            canned_tool_call={
                "tool_name": "calculate_interval",
                "tool_input": {
                    "event_type": "followup.required",
                    "related_event_type": "session.no_show",
                    "max_days": 7,
                },
            },
        )
        tool_name, result = select_and_execute_tool(_make_rule(), "fu1", records, related_ref_id="sess1", 
                                                    reasoner=reasoner)
                
        self.assertEqual(tool_name, "calculate_interval")
        self.assertTrue(result.violated)    # 14 days > 7

    def test_calculate_interval_without_related_ref_id_raises(self):
        reasoner = FakeReasoner(
            canned_response={},
            canned_tool_call={
                "tool_name": "calculate_interval",
                "tool_input": {"event_type": "a", "related_event_type": "b", "max_days": 7}
            }
        )
        with self.assertRaises(ValueError):
            select_and_execute_tool(_make_rule(), "ref1", [], reasoner=reasoner)

    def test_unrecognized_tool_name_raises(self):
        reasoner = FakeReasoner(
            canned_response={},
            canned_tool_call={"tool_name": "not_a_real_tool", "tool_input": {}}
        )
        with self.assertRaises(ValueError):
            select_and_execute_tool(_make_rule(), "ref1", [], reasoner=reasoner)

if __name__ == "__main__":
    unittest.main()