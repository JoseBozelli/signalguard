import unittest

from signalguard.tools.rule_checks import check_event_order, check_prerequisites, calculate_interval

class TestCheckPrerequisite(unittest.TestCase):
    def test_dependent_missing_is_not_a_violation(self):
        result = check_prerequisites([], "ref1", "booked", "completed")
        self.assertFalse(result.violated)

    def test_dependent_present_prerequisite_present_is_fine(self):
        records = [
            {"ref_id": "ref1", "event_type": "booked", "timestamp": "2026-01-01T00:00:00"},
            {"ref_id": "ref1", "event_type": "completed", "timestamp": "2026-01-05T00:00:00"},
        ]
        result = check_prerequisites(records, "ref1", "booked", "completed")
        self.assertFalse(result.violated)

    def test_dependent_present_prerequisite_missing_is_violated(self):
        records = [{"ref_id": "ref1", "event_type": "completed", "timestamp": "2026-01-05T00:00:00"}]
        result = check_prerequisites(records, "ref1", "booked", "completed")
        self.assertTrue(result.violated)
        self.assertIn("no 'booked'", result.reason)

    def test_only_checks_the_given_ref_id(self):
        records = [
            {"ref_id": "ref1", "event_type": "completed", "timestamp": "2026-01-05T00:00:00"},
            {"ref_id": "ref2", "event_type": "booked", "timestamp": "2026-01-01T00:00:00"},
        ]
        result = check_prerequisites(records, "ref1", "booked", "completed")
        self.assertTrue(result.violated)    # ref2's booked record must not "count" for ref1

class TestCheckEventOrder(unittest.TestCase):
    def test_correct_order_is_fine(self):
        records = [
            {"ref_id": "ref1", "event_type": "required", "timestamp": "2026-01-01T00:00:00"},
            {"ref_id": "ref1", "event_type": "completed", "timestamp": "2026-01-02T00:00:00"},
        ]
        result = check_event_order(records, "ref1", "required", "completed")
        self.assertFalse(result.violated)

    def test_reversed_order_is_violated(self):
        records = [
            {"ref_id": "ref1", "event_type": "required", "timestamp": "2026-01-02T00:00:00"},
            {"ref_id": "ref1", "event_type": "completed", "timestamp": "2026-01-01T00:00:00"},
        ]
        result = check_event_order(records, "ref1", "required", "completed")
        self.assertTrue(result.violated)

    def test_missing_either_event_is_not_a_violation(self):
        records = [{"ref_id": "ref1", "event_type": "required", "timestamp": "2026-01-01T00:00:00"}]
        result = check_event_order(records, "ref1", "required", "completed")
        self.assertFalse(result.violated)

class TestCalculateInterval(unittest.TestCase):
    def test_within_window_is_fine(self):
        records = [
            {"ref_id": "s1", "event_type": "no_show", "timestamp": "2026-01-01T00:00:00"},
            {"ref_id": "f1", "event_type": "required", "timestamp": "2026-01-05T00:00:00"},
        ]
        result = calculate_interval(records, "f1", "s1", "required", "no_show", max_days=7)
        self.assertFalse(result.violated)
        self.assertEqual(result.evidence["delta_days"], 4)

    def test_exceeding_window_is_violated(self):
        records = [
            {"ref_id": "s1", "event_type": "no_show", "timestamp": "2026-01-01T00:00:00"},
            {"ref_id": "f1", "event_type": "required", "timestamp": "2026-01-15T00:00:00"},
        ]
        result = calculate_interval(records, "f1", "s1", "required", "no_show", max_days=7)
        self.assertTrue(result.violated)
        self.assertEqual(result.evidence["delta_days"], 14)

    def test_missing_related_event_is_not_a_violation(self):
        records = [{"ref_id": "f1", "event_type": "required", "timestamp": "2026-01-05T00:00:00"}]
        result = calculate_interval(records, "f1", "s1", "required", "no_show", max_days=7)
        self.assertFalse(result.violated)

if __name__ == "__main__":
    unittest.main()