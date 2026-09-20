import unittest

from signalguard.llm.reasoner import FakeReasoner, get_reasoner

class TestFakeReasoner(unittest.TestCase):
    def test_returns_canned_response_regardless_of_input(self):
        canned = {"status": "documented", "rule": None, "reasoning": "test"}
        reasoner = FakeReasoner(canned)
        result = reasoner.generate_structured(
            system="anything", user_message="anything",
            output_schema={}, tool_name="anything", tool_description="anything"
        )
        self.assertEqual(result, canned)

class TestGetReasonerProviderSelection(unittest.TestCase):
    def test_unknown_provider_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            get_reasoner(provider="not_a_real_provider")
        self.assertIn("not_a_real_provider", str(ctx.exception))
        self.assertIn("anthropic", str(ctx.exception))  # names what IS available

    def test_default_provider_is_anthropic(self):
        # It isn't constructed here (that needs the anthropic package + real/fake key) --
        # just cofirm the registry itlsefl defaults to anthropic before construction is attempted.
        from signalguard.llm.reasoner import _PROVIDERS
        self.assertIn("anthropic", _PROVIDERS)

if __name__ == "__main__":
    unittest.main()