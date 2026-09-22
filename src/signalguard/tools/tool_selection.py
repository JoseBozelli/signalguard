"""
LLM-driven bounded tool selection for SignalGuard (Capability 3).

Given a DocumentedRule (already extracted and grounded in documentation) and a specific ref_id under inverstigation,
the LLM selects which of the three bounded tools applies and supplies the RULE-INTERPRETATION parameters only (which
event types are involved, what the timing window is) -- never identifiers like ref_id or the event records themselves.
Those are data-plumbing the orchestration layer supplies directly; asking the model to invent or repeat an ID it was
given is exactly the kind of task Python should own outright (the project deterministic/LLM  separation principle).

The model is deliberately NOT told DocumentedRule.requires_tool before selecting -- that field is extraction's own
guess, and showing it here would make selection a rubber stamp rather than a real choice. Reconciling the two (does
the model's independent choice match extraction's guess, and does it match the hidden answer key's expected_tool)
is a evaluation question.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from signalguard.llm.reasoner import Reasoner, get_reasoner
from signalguard.schemas.documented_rule import DocumentedRule
from signalguard.schemas.tool_result import ToolResult
from signalguard.tools.rule_checks import calculate_interval, check_event_order, check_prerequisites

_SYSTEM_PROMPT = """You determine which single bounded tool should be used to check a documented business rule against
event data, and supply tool's rule-interpretation parameters.

You will be given a documented rule's description and type. Select exactly one tool and provide arguments describing
which event types are involved, based on the rule's own wording. Do not supply any record identifier -- those are 
handled separately by the calling system.

Available tools:
- check_prerequisites: use when the rule requires one event type to be PRESENT before another event type can occur (
a missing-predecessor rule).
- check_event_order: use when the rule requires one event type to occur no later than another, give both occur (a
timestampe-ordering rule).
- calculate_interval: use when the rule imposes a maximum time window (in days) between two event types.
"""

TOOL_SPECS: List[dict[str, Any]] = [
    {
        "name": "check_prerequisites",
        "description": "Check thta a required predecessor event type is present before a dependent event type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prerequisite_event_type": {
                    "type": "string",
                    "description": "The event type that must be present.",
                },
                "dependent_event_type": {
                    "type": "string",
                    "description": "The event type that requires the prerequisite.",
                },
            },
            "required": ["prerequisite_event_type", "dependent_event_type"],
        },
    },
    {
        "name": "check_event_order",
        "description": "Check that one event type occurs no later than another, given both are present.",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_event_type": {
                    "type": "string",
                    "description": "The event type expected to occur first."
                },
                "second_event_type": {
                    "type": "string",
                    "description": "The event type expected to occur second",
                },
            },
            "required": ["first_event_type", "second_event_type"],
        },
    },
    {
        "name": "calculate_interval",
        "description": "Check that the interval between two event types does not exceed a maximum number "
        "of days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "The event type whose timing is being checked.",
                },
                "related_event_type": {
                    "type": "string",
                    "description": "The related/triggering event type the interval is measured from."
                },
                "max_days": {
                    "type": "number",
                    "description": "The maximum allowed number of days between the two events, per the documented rule.",
                },
            },
            "required": ["event_type", "related_event_type", "max_days"],
        },
    },
]

_TOOL_FUNCTIONS = {
    "check_prerequisites": check_prerequisites,
    "check_event_order": check_event_order,
    "calculate_interval": calculate_interval
}

def select_and_execute_tool(
        rule: DocumentedRule,
        ref_id: str,
        records: List[Dict[str, Any]],
        related_ref_id: Optional[str] = None,
        reasoner: Optional[Reasoner] = None
) -> Tuple[str, ToolResult]:
    """
    Asks the LLM to select one of the three bounded tools and suplly its rule-interpretation arguments from `rule`,
    then executes that tool deterministically against `records` for `ref_id` (and `related_ref_id` when the selected
    tools needs a cross-lifecycle reference, i.e., calculate_interval).

    Returns (selected_tool_name, ToolResult) -- the tool name is returned separately so callers/evaluation can compare
    it against the hidden answer key's expected_tool without re-deriving it from the result.
    """
    if reasoner is None:
        reasoner = get_reasoner()

    user_message = (
        f"Rule type: {rule.rule_type.value}\n"
        f"Condition: {rule.condition}\n"
        f"Relevant events: {', '.join(rule.relevant_events)}\n"
        f"Prerequisite (if any): {rule.prerequisite}\n"
        f"Temporal constraint (if any): {rule.temporal_constraint}\n\n"
        "Select the correct tool and provide its arguments."
    )

    call = reasoner.call_with_tools(
        system=_SYSTEM_PROMPT,
        user_message=user_message,
        tools=TOOL_SPECS,
        tool_choice={"type": "any"}
    )

    tool_name = call["tool_name"]
    tool_input = dict(call["tool_input"])

    if tool_name not in _TOOL_FUNCTIONS:
        raise ValueError(f"Model selected an unrecognized tool: {tool_name}")

    tool_input["records"] = records
    tool_input["ref_id"] = ref_id
    if tool_name == "calculate_interval":
        if related_ref_id is None:
            raise ValueError("calculate_interval requires related_ref_id, but none was supplied.")
        tool_input["related_ref_id"] = related_ref_id

    result = _TOOL_FUNCTIONS[tool_name](**tool_input)
    return tool_name, result