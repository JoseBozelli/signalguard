import unittest
from pathlib import Path

from signalguard.rag.chunking import chunk_corpus, chunk_markdown_file, slugify

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"


class TestSlugify(unittest.TestCase):
    def test_basic_slug(self):
        self.assertEqual(slugify("Session Booking and Completion"), "session-booking-and-completion")

    def test_preserves_existing_hyphens_no_doubling(self):
        self.assertEqual(
            slugify("Follow-Up Response Window After a Missed Session"),
            "follow-up-response-window-after-a-missed-session",
        )

    def test_strips_punctuation(self):
        self.assertEqual(slugify("What's Allowed? (Really!)"), "whats-allowed-really")


class TestChunkCorpusStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = chunk_corpus(DOCS_DIR)
        cls.by_id = {c.chunk_id: c for c in cls.chunks}

    def test_four_docs_found(self):
        source_files = {c.source_file for c in self.chunks}
        self.assertEqual(
            source_files,
            {
                "event-lifecycle-rules.md",
                "sla-and-timing-policies.md",
                "event-field-reference.md",
                "exceptions-and-known-limitations.md",
            },
        )

    def test_no_duplicate_chunk_ids(self):
        ids = [c.chunk_id for c in self.chunks]
        self.assertEqual(len(ids), len(set(ids)), "chunk_ids must be unique across the whole corpus")

    def test_overview_sections_excluded_from_nothing_but_are_chunks_too(self):
        # "## Overview" sections are real chunks (distractor-adjacent, not
        # rule content) -- confirming they're present, not silently dropped.
        self.assertIn("event-lifecycle-rules.md::overview", self.by_id)
        self.assertIn("sla-and-timing-policies.md::overview", self.by_id)

    def test_document_title_and_preamble_not_chunked(self):
        for chunk in self.chunks:
            self.assertNotIn("# Event Lifecycle Rules", chunk.text)


class TestChunkIdsMatchAnswerKeyGoldLabels(unittest.TestCase):
    """
    This is the regression test that matters most: the chunk IDs the
    chunker actually produces must exactly match the chunk IDs already
    hardcoded into injector.RULE_CHUNK_MAP (and therefore into every
    Tier-2 AnswerKeyEntry.expected_doc_chunk_ids). If these drift apart,
    retrieval-recall metric compares against chunk IDs that don't
    exist in the real index -- silently scoring every retrieval as a miss.
    """

    @classmethod
    def setUpClass(cls):
        cls.chunk_ids = {c.chunk_id for c in chunk_corpus(DOCS_DIR)}

    def test_r1_gold_chunk_exists(self):
        self.assertIn("event-lifecycle-rules.md::session-booking-and-completion", self.chunk_ids)

    def test_r2_gold_chunk_exists(self):
        self.assertIn("event-lifecycle-rules.md::task-completion-requirements", self.chunk_ids)

    def test_r3_r4_gold_chunk_exists(self):
        self.assertIn("event-lifecycle-rules.md::follow-up-completion-requirements", self.chunk_ids)

    def test_r5_gold_chunk_exists(self):
        self.assertIn(
            "sla-and-timing-policies.md::follow-up-response-window-after-a-missed-session",
            self.chunk_ids,
        )


if __name__ == "__main__":
    unittest.main()