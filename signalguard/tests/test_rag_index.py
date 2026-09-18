import unittest
from pathlib import Path

from signalguard.rag.chunking import chunk_corpus
from signalguard.rag.embeddings import FakeEmbedder
from signalguard.rag.index import build_index, retrieve

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs_corpus"


class TestRagIndexWithFakeEmbedder(unittest.TestCase):
    """
    Uses FakeEmbedder (no network, no API key) to test index plumbing --
    NOT retrieval quality, which FakeEmbedder cannot meaningfully test
    since it isn't semantic. Real retrieval-quality evaluation 
    runs against VoyageEmbedder.
    """

    @classmethod
    def setUpClass(cls):
        cls.embedder = FakeEmbedder()
        cls.chunks = chunk_corpus(DOCS_DIR)
        cls.collection = build_index(DOCS_DIR, cls.embedder, persist_directory=None)

    def test_all_chunks_indexed(self):
        self.assertEqual(self.collection.count(), len(self.chunks))

    def test_querying_a_chunks_own_text_retrieves_it_first(self):
        # FakeEmbedder is a pure function of text, so embedding a chunk's
        # own text as a "query" must produce (near-)identical vectors to
        # what that chunk was indexed with -- it should come back as the
        # single best match every time.
        target = self.chunks[0]
        results = retrieve(self.collection, target.text, self.embedder, k=3)
        self.assertEqual(results[0].chunk_id, target.chunk_id)

    def test_retrieve_returns_k_results(self):
        results = retrieve(self.collection, "any query text", self.embedder, k=3)
        self.assertEqual(len(results), 3)

    def test_retrieval_results_carry_metadata(self):
        results = retrieve(self.collection, "any query text", self.embedder, k=1)
        self.assertTrue(results[0].source_file.endswith(".md"))
        self.assertTrue(results[0].heading)

    def test_scores_are_descending(self):
        results = retrieve(self.collection, "any query text", self.embedder, k=5)
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()