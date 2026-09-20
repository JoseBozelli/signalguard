import unittest
from dataclasses import dataclass

from signalguard.extraction.rule_extraction import _build_context

@dataclass
class FakeChunk:
    chunk_id: str
    source_file: str
    heading: str
    text: str

class TestBuildContext(unittest.TestCase):
    """
    Tests only the deterministic, network-free part of extraction: how retrieved chunks get formated into
    the prompt context. The actual model call (extracted_rule) is NOT unit tested here -- it's non-deterministic
    and billed, so it's covered by scripts/smoke_test_extraction.py instead, run by hand.
    """

    def test_single_chunk_formatting(self):
        chunk = FakeChunk(chunk_id="doc.md::heading", source_file="doc.md", heading="Heading", text="Body text.")
        context = _build_context([chunk])
        self.assertIn("chunk_id: doc.md::heading", context)
        self.assertIn("doc.md", context)
        self.assertIn("Heading", context)
        self.assertIn("Body text.", context)

    def test_multiple_chunks_separated(self):
        c1 = FakeChunk("a::1", "a.md", "H1", "T1")
        c2 = FakeChunk("a::2", "a.md", "H2", "T2")
        context = _build_context([c1, c2])
        self.assertIn("T1", context)
        self.assertIn("T2", context)
        self.assertLess(context.index("T1"), context.index("T2"))

    def test_empty_chunks_returns_empty_string(self):
        self.assertEqual(_build_context([]), "")

if __name__ == "__main__":
    unittest.main()