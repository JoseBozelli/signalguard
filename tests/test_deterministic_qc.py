import unittest

from signalguard.data.generator import generate_clean_dataset
from signalguard.data.injector import inject_defects
from signalguard.qc.deterministic import (
    check_duplicate_event_ids,
    check_missing_account_id,
    check_invalid_event_type,
    run_baseline_qc,
)


class TestDeterministicQCUnit(unittest.TestCase):
    """Small hand-built record sets, independent of the generator/injector."""

    def test_duplicate_event_id_detected(self):
        records = [
            {"event_id": "e1", "account_id": "a1", "event_type": "task.required"},
            {"event_id": "e1", "account_id": "a1", "event_type": "task.completed"},
            {"event_id": "e2", "account_id": "a1", "event_type": "session.booked"},
        ]
        findings = check_duplicate_event_ids(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].defect_type, "duplicate_event_id")
        self.assertEqual(findings[0].reasoning_category, "fact")
        self.assertEqual(findings[0].source, "deterministic_qc")

    def test_duplicate_event_id_only_reported_once_for_triples(self):
        records = [
            {"event_id": "e1", "account_id": "a1", "event_type": "task.required"},
            {"event_id": "e1", "account_id": "a1", "event_type": "task.completed"},
            {"event_id": "e1", "account_id": "a1", "event_type": "session.booked"},
        ]
        findings = check_duplicate_event_ids(records)
        self.assertEqual(len(findings), 1)

    def test_no_duplicates_produces_no_findings(self):
        records = [
            {"event_id": "e1", "account_id": "a1", "event_type": "task.required"},
            {"event_id": "e2", "account_id": "a1", "event_type": "task.completed"},
        ]
        self.assertEqual(check_duplicate_event_ids(records), [])

    def test_missing_account_id_detected_for_none_and_empty(self):
        records = [
            {"event_id": "e1", "account_id": None, "event_type": "task.required"},
            {"event_id": "e2", "account_id": "", "event_type": "task.required"},
            {"event_id": "e3", "account_id": "a1", "event_type": "task.required"},
        ]
        findings = check_missing_account_id(records)
        self.assertEqual(len(findings), 2)
        self.assertEqual({f.affected_event_ids[0] for f in findings}, {"e1", "e2"})

    def test_invalid_event_type_detected(self):
        records = [
            {"event_id": "e1", "account_id": "a1", "event_type": "session.rescheduled"},
            {"event_id": "e2", "account_id": "a1", "event_type": "task.required"},
        ]
        findings = check_invalid_event_type(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].affected_event_ids, ["e1"])

    def test_valid_records_produce_no_findings_at_all(self):
        records = [
            {"event_id": "e1", "account_id": "a1", "event_type": "task.required"},
            {"event_id": "e2", "account_id": "a1", "event_type": "task.completed"},
        ]
        self.assertEqual(run_baseline_qc(records), [])


class TestDeterministicQCOnCorruptedDataset(unittest.TestCase):
    """
    This is Baseline A's real evaluation: run it against the actual
    corrupted dataset and score it against the hidden answer key. This is
    the number that later gets compared to System B's Tier-2 performance.
    """

    @classmethod
    def setUpClass(cls):
        events = generate_clean_dataset(num_accounts=80, seed=42)
        cls.records, cls.answer_key = inject_defects(events, seed=7, instances_per_defect_type=5)
        cls.findings = run_baseline_qc(cls.records)

    @staticmethod
    def _matches(finding, entry) -> bool:
        return finding.defect_type == entry.defect_type and bool(
            set(finding.affected_event_ids) & set(entry.affected_event_ids)
        )

    def test_baseline_recall_is_complete_on_tier1(self):
        tier1_entries = [e for e in self.answer_key if e.tier == "tier1"]
        caught = sum(1 for e in tier1_entries if any(self._matches(f, e) for f in self.findings))
        self.assertEqual(caught, len(tier1_entries), "Baseline A should catch every Tier-1 defect")

    def test_baseline_recall_is_zero_on_tier2(self):
        tier2_entries = [e for e in self.answer_key if e.tier == "tier2"]
        caught = sum(1 for e in tier2_entries if any(self._matches(f, e) for f in self.findings))
        self.assertEqual(caught, 0, "Baseline A has no rule knowledge and must miss every Tier-2 defect")

    def test_baseline_has_no_false_positives(self):
        # 15 Tier-1 defects were injected; Baseline A should report exactly
        # 15 findings, no more (no spurious flags on clean records).
        self.assertEqual(len(self.findings), 15)

    def test_all_findings_are_deterministic_and_factual(self):
        for f in self.findings:
            self.assertEqual(f.source, "deterministic_qc")
            self.assertEqual(f.reasoning_category, "fact")
            self.assertIsNone(f.confidence)
            self.assertIsNone(f.rule_id)


if __name__ == "__main__":
    unittest.main()