import unittest

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects
from signalguard.tools.rule_checks import calculate_interval, check_event_order, check_prerequisites

class TestToolsAgainstRealBenchmark(unittest.TestCase):
    """
    Validates that the tool functions catch actual Tier-2 defects in the real corrupted benchmark dataset, when
    given the correct rule parameters -- proving the tools work correctly BEFORE the LLM  tool-selection layer
    (next step) is built on top of them. If tool selection ever misbehaves later, this test isolates whether the fault
    is in tool logic or in LLM tool selection.
    """

    @classmethod
    def setUpClass(cls):
        events = generate_clean_dataset(num_accounts=80, seed=42)
        cls.records, cls.answer_key = inject_defects(events, seed=7, instances_per_defect_type=5)

    def test_check_prerequisite_catches_all_r1_defects(self):
        r1_entries = [e for e in self.answer_key if e.rule_id == "R1"]
        self.assertEqual(len(r1_entries), 5)
        for entry in r1_entries:
            result = check_prerequisites(self.records, entry.affected_ref_id, "session.booked", "session.completed")
            self.assertTrue(result.violated, f"expected a violation for ref_id={entry.affected_ref_id}")

    def test_check_event_order_catches_all_r2_defects(self):
        r2_entries = [e for e in self.answer_key if e.rule_id == "R2"]
        self.assertEqual(len(r2_entries), 5)
        for entry in r2_entries:
            result = check_event_order(self.records, entry.affected_ref_id, "task.required", "task.completed")
            self.assertTrue(result.violated, f"expected a violation for ref_id={entry.affected_ref_id}")

    def test_calculate_interval_catches_all_r5_defects(self):
        r5_entries = [e for e in self.answer_key if e.rule_id == "R5"]
        self.assertEqual(len(r5_entries), 5)
        for entry in r5_entries:
            followup_record = next(r for r in self.records if r["event_id"] == entry.affected_event_ids[0])
            result = calculate_interval(
                self.records,
                ref_id=entry.affected_ref_id,
                related_ref_id=followup_record["related_ref_id"],
                event_type="followup.required",
                related_event_type="session.no_show",
                max_days=7
            )
            self.assertTrue(result.violated, f"expected a violation for ref_id={entry.affected_ref_id}")

    def test_tools_do_not_flag_clean_lifecycles(self):
        # Sanity check: pick non-defect ref_ids and confirm the tools correctly report no violation --
        # proving these aren't tools that simply always say "violated".
        defect_ref_ids = {e.affected_ref_id for e in self.answer_key if e.affected_ref_id}

        clean_session_refs = [
            r["ref_id"] for r in self.records
            if r["event_type"] == "session.completed" and r["ref_id"] not in defect_ref_ids
        ][:5]
        self.assertGreater(len(clean_session_refs), 0, "test setup issue: no clean session refs found")
        for ref_id in clean_session_refs:
            result = check_prerequisites(self.records, ref_id, "session.booked", "session.completed")
            self.assertFalse(result.violated)

        clean_task_refs = [
            r["ref_id"] for r in self.records
            if r["event_type"] == "task.required" and r["ref_id"] not in defect_ref_ids
        ][:5]
        self.assertGreater(len(clean_task_refs), 0, "test setup issue: no clean task refs found")
        for ref_id in clean_task_refs:
            result = check_event_order(self.records, ref_id, "task.required", "task.completed")
            self.assertFalse(result.violated)

if __name__ == "__main__":
    unittest.main()