import json
import tempfile
import unittest
from pathlib import Path

from signalguard.observability.tracing import JSONLTracer, new_run_id


class TestNewRunId(unittest.TestCase):
    def test_returns_a_short_hex_string(self):
        run_id = new_run_id()
        self.assertEqual(len(run_id), 12)
        int(run_id, 16)  # raises ValueError if not valid hex

    def test_successive_calls_are_unique(self):
        ids = {new_run_id() for _ in range(20)}
        self.assertEqual(len(ids), 20)


class TestJSONLTracer(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.trace_path = Path(self._tmpdir.name) / "traces" / "test.jsonl"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_creates_parent_directory_automatically(self):
        self.assertFalse(self.trace_path.parent.exists())
        JSONLTracer(self.trace_path)
        self.assertTrue(self.trace_path.parent.exists())

    def test_log_appends_one_line_per_call(self):
        tracer = JSONLTracer(self.trace_path)
        tracer.log({"event": "first"})
        tracer.log({"event": "second"})

        with open(self.trace_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)

    def test_log_adds_a_timestamp(self):
        tracer = JSONLTracer(self.trace_path)
        tracer.log({"event": "first"})

        records = tracer.read_all()
        self.assertIn("logged_at", records[0])
        self.assertEqual(records[0]["event"], "first")

    def test_read_all_returns_records_in_write_order(self):
        tracer = JSONLTracer(self.trace_path)
        tracer.log({"index": 0})
        tracer.log({"index": 1})
        tracer.log({"index": 2})

        records = tracer.read_all()
        self.assertEqual([r["index"] for r in records], [0, 1, 2])

    def test_read_all_on_nonexistent_file_returns_empty_list(self):
        tracer = JSONLTracer(self.trace_path)
        self.assertEqual(tracer.read_all(), [])

    def test_non_json_native_values_are_stringified_not_broken(self):
        # e.g. a Path object or other non-serializable value shouldn't crash
        # logging. Compared against str(Path(...)) rather than a hardcoded
        # literal: path separators are platform-dependent (\ on Windows).
        tracer = JSONLTracer(self.trace_path)
        sample_path = Path("/some/path")
        tracer.log({"path_value": sample_path})

        records = tracer.read_all()
        self.assertEqual(records[0]["path_value"], str(sample_path))

    def test_file_is_valid_jsonl_line_by_line(self):
        tracer = JSONLTracer(self.trace_path)
        tracer.log({"a": 1})
        tracer.log({"b": 2})

        with open(self.trace_path) as f:
            for line in f:
                json.loads(line)  # raises if any line isn't valid standalone JSON


if __name__ == "__main__":
    unittest.main()