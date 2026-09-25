"""
LLM reasoning provider interface for SignalGuard.

This project's own choice is Claude/Anthropic for structured extraction
and, later, bounded tool calling (see the Day-1 provider comparison: one
tool-use mechanism serves both capabilities, minimizing implementation
surface for a one-week project). Nothing in extraction or orchestration
code should hard-depend on that choice, though -- `Reasoner` is the swap
point. To run SignalGuard against a different provider, implement
`generate_structured` against that provider's own structured-output
mechanism (function calling, JSON mode, etc.) and register it in
`get_reasoner()`; no other module needs to change.

Only ClaudeReasoner is implemented here. A second provider (e.g. OpenAI)
is intentionally NOT pre-built -- an implementation with no API key to
verify it and no test coverage would be unverified scope, not a working
feature. The Protocol below is what makes adding one later a contained,
one-file change.

FakeReasoner exists for the same reason FakeEmbedder does: tests and any
CI pipeline must not require a paid, non-deterministic API call.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol


class Reasoner(Protocol):
    def generate_structured(
        self,
        *,
        system: str,
        user_message: str,
        output_schema: dict,
        tool_name: str,
        tool_description: str,
    ) -> dict:
        """
        Ask the model to produce output matching output_schema (a JSON
        Schema dict, e.g. from a Pydantic model's model_json_schema())
        and return it as a plain dict. Implementations own however their
        provider forces schema-shaped output -- callers never need to
        know which mechanism was used underneath.
        """
        ...

    def call_with_tools(
        self,
        *,
        system: str,
        user_message: str,
        tools: list,
        tool_choice: dict,
    ) -> dict:
        """
        Offer the model several tools (each a dict with name, description,
        input_schema) and let it select one, honoring tool_choice (e.g.
        {"type": "any"} to force some tool call, {"type": "tool", "name": X}
        to force a specific one). Returns {"tool_name": str, "tool_input": dict}
        for whichever tool was actually called.

        This is the genuine multi-tool-selection primitive; generate_structured
        is the special case of always forcing exactly one known tool.
        """
        ...


class ClaudeReasoner:
    """This project's chosen provider. Uses Claude's tool-use API with a
    forced tool_choice to guarantee schema-shaped output."""

    # Current as of this writing -- see docs.claude.com for up-to-date pricing.
    INPUT_COST_PER_MILLION_TOKENS = 3.00
    OUTPUT_COST_PER_MILLION_TOKENS = 15.00

    def __init__(self, model: str = "claude-sonnet-4-6", secrets_path: str = ".secrets"):
        from dotenv import load_dotenv
        import anthropic

        load_dotenv(secrets_path)
        self._client = anthropic.Anthropic()
        self._model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.total_input_tokens / 1_000_000 * self.INPUT_COST_PER_MILLION_TOKENS
            + self.total_output_tokens / 1_000_000 * self.OUTPUT_COST_PER_MILLION_TOKENS
        )

    def _record_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.total_input_tokens += getattr(usage, "input_tokens", 0)
            self.total_output_tokens += getattr(usage, "output_tokens", 0)

    def generate_structured(
        self,
        *,
        system: str,
        user_message: str,
        output_schema: dict,
        tool_name: str,
        tool_description: str,
    ) -> dict:
        schema = dict(output_schema)
        schema.pop("title", None)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        tool_use_block = next(b for b in response.content if b.type == "tool_use")
        self._record_usage(response)
        return tool_use_block.input

    def call_with_tools(
        self,
        *,
        system: str,
        user_message: str,
        tools: list,
        tool_choice: dict,
    ) -> dict:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=tools,
            tool_choice=tool_choice,
        )
        tool_use_block = next(b for b in response.content if b.type == "tool_use")
        self._record_usage(response)
        return {"tool_name": tool_use_block.name, "tool_input": tool_use_block.input}


class FakeReasoner:
    """
    Deterministic, network-free reasoner for tests. Always returns a
    fixed, caller-supplied response regardless of input -- it does not
    reason at all. Tests orchestration/plumbing (does the caller pass the
    right schema, correctly parse the result) -- never extraction quality.
    """

    def __init__(self, canned_response: dict, canned_tool_call: Optional[dict] = None):
        self._canned_response = canned_response
        self._canned_tool_call = canned_tool_call

    def generate_structured(
        self,
        *,
        system: str,
        user_message: str,
        output_schema: dict,
        tool_name: str,
        tool_description: str,
    ) -> dict:
        return self._canned_response

    def call_with_tools(
        self,
        *,
        system: str,
        user_message: str,
        tools: list,
        tool_choice: dict,
    ) -> dict:
        if self._canned_tool_call is None:
            raise ValueError("FakeReasoner was not given a canned_tool_call to return.")
        return self._canned_tool_call


# Registry of available providers. Adding a new one is: implement Reasoner,
# add one line here.
_PROVIDERS = {"anthropic": ClaudeReasoner}


def get_reasoner(provider: Optional[str] = None, model: Optional[str] = None) -> Reasoner:
    """
    Config-driven provider selection. Reads SIGNALGUARD_LLM_PROVIDER /
    SIGNALGUARD_LLM_MODEL from the environment when not passed explicitly
    -- switching providers is then a config change, not a code change,
    provided a Reasoner implementation for that provider is registered.
    """
    provider = provider or os.environ.get("SIGNALGUARD_LLM_PROVIDER", "anthropic")
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. Available: {list(_PROVIDERS)}. "
            "To add another provider, implement the Reasoner protocol and register it in _PROVIDERS."
        )

    kwargs = {}
    env_model = model or os.environ.get("SIGNALGUARD_LLM_MODEL")
    if env_model:
        kwargs["model"] = env_model

    return _PROVIDERS[provider](**kwargs)