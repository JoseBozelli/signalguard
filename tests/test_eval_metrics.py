import unittest

from signalguard.eval.metrics import (
    compute_detection_metrics,
    compute_retrieval_hit,
    compute_retrieval_recall_at_k,
    compute_tool_selection_accuracy,
)
from signalguard.schemas.answer_key import AnswerKeyEntry
from signalguard.schemas.finding import Finding


def _entry(defect_id, tier="tier2", event_ids=None):
    return AnswerKeyEntry(
        defect_id=defect_id,
        tier=tier,
        defect_type="test_defect",
        account_id="a1",
        affected_event_ids=event_ids or [f"e-{defect_id}"],
        description="test entry",
    )


def _finding(tier="tier2", event_ids=None):
    return Finding(
        source="ai_pipeline",
        tier=tier,
        defect_type="test_defect",
        affected_event_ids=event_ids or ["e-d1"],
        evidence="test evidence",
        reasoning_category="documented_rule",
        recommended_action="review",
    )


class TestComputeDetectionMetrics(unittest.TestCase):
    def test_perfect_match_is_all_true_positive(self):
        answer_key = [_entry("d1", event_ids=["e1"]), _entry("d2", event_ids=["e2"])]
        findings = [_finding(event_ids=["e1"]), _finding(event_ids=["e2"])]

        metrics = compute_detection_metrics(findings, answer_key)
        self.assertEqual(metrics.true_positives, 2)
        self.assertEqual(metrics.false_positives, 0)
        self.assertEqual(metrics.false_negatives, 0)
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)
        self.assertEqual(metrics.f1, 1.0)

    def test_missed_defect_is_false_negative(self):
        answer_key = [_entry("d1", event_ids=["e1"]), _entry("d2", event_ids=["e2"])]
        findings = [_finding(event_ids=["e1"])]  # d2 never found

        metrics = compute_detection_metrics(findings, answer_key)
        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.false_negatives, 1)
        self.assertEqual(metrics.recall, 0.5)

    def test_spurious_finding_is_false_positive(self):
        answer_key = [_entry("d1", event_ids=["e1"])]
        findings = [_finding(event_ids=["e1"]), _finding(event_ids=["e999"])]  # e999 matches nothing

        metrics = compute_detection_metrics(findings, answer_key)
        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.false_positives, 1)
        self.assertAlmostEqual(metrics.precision, 0.5)

    def test_duplicate_finding_for_same_defect_counts_as_one_tp_one_fp(self):
        answer_key = [_entry("d1", event_ids=["e1"])]
        findings = [_finding(event_ids=["e1"]), _finding(event_ids=["e1"])]  # reported twice

        metrics = compute_detection_metrics(findings, answer_key)
        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.false_positives, 1)
        self.assertEqual(metrics.false_negatives, 0)

    def test_no_findings_and_no_defects_gives_zero_not_nan(self):
        metrics = compute_detection_metrics([], [])
        self.assertEqual(metrics.precision, 0.0)
        self.assertEqual(metrics.recall, 0.0)
        self.assertEqual(metrics.f1, 0.0)

    def test_tier_filter_isolates_tier1_from_tier2(self):
        answer_key = [_entry("d1", tier="tier1", event_ids=["e1"]), _entry("d2", tier="tier2", event_ids=["e2"])]
        findings = [_finding(tier="tier2", event_ids=["e2"])]

        tier1_metrics = compute_detection_metrics(findings, answer_key, tier="tier1")
        tier2_metrics = compute_detection_metrics(findings, answer_key, tier="tier2")

        self.assertEqual(tier1_metrics.true_positives, 0)
        self.assertEqual(tier1_metrics.false_negatives, 1)  # d1 never addressed by a tier2 finding
        self.assertEqual(tier2_metrics.true_positives, 1)
        self.assertEqual(tier2_metrics.false_negatives, 0)


class TestRetrievalMetrics(unittest.TestCase):
    def test_hit_when_any_gold_chunk_retrieved(self):
        self.assertTrue(compute_retrieval_hit(["a", "b", "c"], ["c", "z"]))

    def test_no_hit_when_no_overlap(self):
        self.assertFalse(compute_retrieval_hit(["a", "b"], ["z"]))

    def test_recall_at_k_aggregation(self):
        self.assertEqual(compute_retrieval_recall_at_k([True, True, False, True]), 0.75)

    def test_recall_at_k_empty_is_zero_not_error(self):
        self.assertEqual(compute_retrieval_recall_at_k([]), 0.0)


class TestToolSelectionAccuracy(unittest.TestCase):
    def test_all_correct(self):
        self.assertEqual(compute_tool_selection_accuracy([("a", "a"), ("b", "b")]), 1.0)

    def test_partial_correct(self):
        self.assertEqual(compute_tool_selection_accuracy([("a", "a"), ("b", "c")]), 0.5)

    def test_empty_is_zero_not_error(self):
        self.assertEqual(compute_tool_selection_accuracy([]), 0.0)


if __name__ == "__main__":
    unittest.main()