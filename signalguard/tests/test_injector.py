import unittest
from datetime import datetime
from collections import Counter

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects


class TestInjector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clean_events = generate_clean_dataset(num_accounts=80, seed=42)
        cls.records, cls.answer_key = inject_defects(
            cls.clean_events, seed=7, instances_per_defect_type=5
        )
        cls.records_by_id = {r["event_id"]: r for r in cls.records}

    def test_answer_key_has_30_entries(self):
        self.assertEqual(len(self.answer_key), 30)

    def test_five_instances_per_defect_type(self):
        counts = Counter(e.defect_type for e in self.answer_key)
        for defect_type, count in counts.items():
            self.assertEqual(count, 5, f"{defect_type} has {count} instances, expected 5")
        self.assertEqual(len(counts), 6, "expected exactly 6 distinct defect types")

    def test_tier_split_is_3_and_3(self):
        tiers = Counter(e.tier for e in self.answer_key)
        self.assertEqual(tiers["tier1"], 15)
        self.assertEqual(tiers["tier2"], 15)

    def test_no_affected_event_overlap_across_entries(self):
        seen = set()
        for entry in self.answer_key:
            for eid in entry.affected_event_ids:
                self.assertNotIn(eid, seen, f"event_id {eid} implicated in more than one defect")
                seen.add(eid)

    def test_duplicate_event_id_defects_actually_duplicate(self):
        dup_entries = [e for e in self.answer_key if e.defect_type == "duplicate_event_id"]
        self.assertEqual(len(dup_entries), 5)
        for entry in dup_entries:
            shared_id = entry.affected_event_ids[0]
            matching = [r for r in self.records if r["event_id"] == shared_id]
            self.assertGreaterEqual(len(matching), 2, f"expected >=2 records with event_id {shared_id}")

    def test_missing_account_id_defects_are_null(self):
        entries = [e for e in self.answer_key if e.defect_type == "missing_account_id"]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            record = self.records_by_id[entry.affected_event_ids[0]]
            self.assertIsNone(record["account_id"])

    def test_invalid_event_type_defects_are_undocumented(self):
        entries = [e for e in self.answer_key if e.defect_type == "invalid_event_type"]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            record = self.records_by_id[entry.affected_event_ids[0]]
            self.assertEqual(record["event_type"], "session.rescheduled")

    def test_missing_prerequisite_r1_actually_missing(self):
        entries = [e for e in self.answer_key if e.rule_id == "R1"]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            same_ref = [r for r in self.records if r.get("ref_id") == entry.affected_ref_id]
            types = {r["event_type"] for r in same_ref}
            self.assertNotIn("session.booked", types)
            self.assertIn("session.completed", types)
            self.assertEqual(entry.expected_tool, "check_prerequisite")

    def test_bad_ordering_r2_actually_out_of_order(self):
        entries = [e for e in self.answer_key if e.rule_id == "R2"]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            same_ref = [r for r in self.records if r.get("ref_id") == entry.affected_ref_id]
            required_ts = next(datetime.fromisoformat(r["timestamp"]) for r in same_ref if r["event_type"] == "task.required")
            completed_ts = next(datetime.fromisoformat(r["timestamp"]) for r in same_ref if r["event_type"] == "task.completed")
            self.assertGreater(required_ts, completed_ts, "expected task.required to now be AFTER task.completed")
            self.assertEqual(entry.expected_tool, "check_event_order")

    def test_timing_window_r5_actually_exceeds_sla(self):
        entries = [e for e in self.answer_key if e.rule_id == "R5"]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            record = self.records_by_id[entry.affected_event_ids[0]]
            no_show = next(
                r for r in self.records
                if r["event_type"] == "session.no_show" and r.get("ref_id") == record["related_ref_id"]
            )
            delta_days = (datetime.fromisoformat(record["timestamp"]) - datetime.fromisoformat(no_show["timestamp"])).days
            self.assertGreater(delta_days, 7)
            self.assertEqual(entry.expected_tool, "calculate_interval")

    def test_tier1_entries_have_no_rule_or_tool(self):
        for entry in self.answer_key:
            if entry.tier == "tier1":
                self.assertIsNone(entry.rule_id)
                self.assertIsNone(entry.expected_tool)

    def test_deterministic_with_fixed_seed(self):
        # event_id is uuid4-random and NOT reproducible across calls even
        # with a fixed injector seed (it's generated at Event-construction
        # time, upstream of the injector's own RNG). Determinism is judged
        # by WHICH records get corrupted (defect_type + ref_id + rule_id),
        # not by the random IDs those records happen to carry.
        events_a = generate_clean_dataset(num_accounts=80, seed=42)
        _, key_a = inject_defects(events_a, seed=7, instances_per_defect_type=5)
        events_b = generate_clean_dataset(num_accounts=80, seed=42)
        _, key_b = inject_defects(events_b, seed=7, instances_per_defect_type=5)

        shape = lambda key: [(e.defect_type, e.rule_id, e.affected_ref_id) for e in key]
        self.assertEqual(shape(key_a), shape(key_b))


if __name__ == "__main__":
    unittest.main()