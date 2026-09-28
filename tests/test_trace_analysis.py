import unittest

from signalguard.eval.trace_analysis import format_report, summarize_traces


def _seeded(rule_id, expected_tool, selected_tool, run_id="r1"):
    return {
        "run_id": run_id,
        "candidate_kind": "seeded_defect",
        "rule_id": rule_id,
        "expected_tool": expected_tool,
        "selected_tool": selected_tool,
        "extraction_status": "documented",
        "finding": {"evidence": "violation"},
    }


def _clean(finding=None, run_id="r1"):
    return {
        "run_id": run_id,
        "candidate_kind": "clean_control",
        "rule_id": None,
        "expected_tool": None,
        "event_type": "session.completed",
        "ref_id": "sess_1",
        "selected_tool": "check_prerequisite",
        "extraction_status": "documented",
        "finding": finding,
    }


class TestSummarizeTraces(unittest.TestCase):
    def test_counts_records_by_kind(self):
        records = [_seeded("R1", "a", "a"), _clean(), _clean()]
        summary = summarize_traces(records)
        self.assertEqual(summary["total_records"], 3)
        self.assertEqual(summary["seeded_defect_records"], 1)
        self.assertEqual(summary["clean_control_records"], 2)

    def test_full_agreement_when_names_match(self):
        records = [_seeded("R1", "check_prerequisite", "check_prerequisite") for _ in range(5)]
        info = summarize_traces(records)["tool_agreement_by_rule"]["R1"]
        self.assertEqual(info["total"], 5)
        self.assertEqual(info["matches"], 5)

    def test_naming_mismatch_shows_as_zero_agreement_with_both_names_visible(self):
        # The motivating case: correct behavior, but the selected tool's
        # name differs from the answer key's by one letter.
        records = [_seeded("R1", "check_prerequisite", "check_prerequisites") for _ in range(5)]
        info = summarize_traces(records)["tool_agreement_by_rule"]["R1"]
        self.assertEqual(info["matches"], 0)
        self.assertEqual(info["expected_tool"], "check_prerequisite")
        self.assertEqual(info["selected_tools"], {"check_prerequisites": 5})

    def test_agreement_is_tracked_separately_per_rule(self):
        records = (
            [_seeded("R1", "check_prerequisite", "check_prerequisites") for _ in range(5)]
            + [_seeded("R2", "check_event_order", "check_event_order") for _ in range(5)]
        )
        by_rule = summarize_traces(records)["tool_agreement_by_rule"]
        self.assertEqual(by_rule["R1"]["matches"], 0)
        self.assertEqual(by_rule["R2"]["matches"], 5)

    def test_abstention_with_no_selected_tool_is_not_a_match(self):
        records = [_seeded("R1", "check_prerequisite", None)]
        info = summarize_traces(records)["tool_agreement_by_rule"]["R1"]
        self.assertEqual(info["matches"], 0)

    def test_false_positives_are_only_clean_controls_with_findings(self):
        records = [
            _clean(finding=None),
            _clean(finding={"evidence": "spurious violation"}),
            _seeded("R1", "a", "a"),  # a seeded defect with a finding is NOT a false positive
        ]
        false_positives = summarize_traces(records)["false_positives"]
        self.assertEqual(len(false_positives), 1)
        self.assertEqual(false_positives[0]["evidence"], "spurious violation")

    def test_extraction_status_counts(self):
        records = [
            {"extraction_status": "documented"},
            {"extraction_status": "documented"},
            {"extraction_status": "insufficient_evidence"},
        ]
        counts = summarize_traces(records)["extraction_status_counts"]
        self.assertEqual(counts, {"documented": 2, "insufficient_evidence": 1})

    def test_empty_input_does_not_crash(self):
        summary = summarize_traces([])
        self.assertEqual(summary["total_records"], 0)
        self.assertEqual(summary["false_positives"], [])


class TestFormatReport(unittest.TestCase):
    def test_flags_mismatched_rules(self):
        records = [_seeded("R1", "check_prerequisite", "check_prerequisites")]
        report = format_report(summarize_traces(records))
        self.assertIn("MISMATCH", report)
        self.assertIn("check_prerequisites", report)

    def test_no_mismatch_flag_when_everything_agrees(self):
        records = [_seeded("R1", "check_prerequisite", "check_prerequisite")]
        report = format_report(summarize_traces(records))
        self.assertNotIn("MISMATCH", report)

    def test_lists_false_positive_details(self):
        records = [_clean(finding={"evidence": "spurious violation"})]
        report = format_report(summarize_traces(records))
        self.assertIn("False positives on clean controls: 1", report)
        self.assertIn("spurious violation", report)


if __name__ == "__main__":
    unittest.main()