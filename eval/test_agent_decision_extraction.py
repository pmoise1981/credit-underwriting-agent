# Deterministic unit tests for agent.py's decision extraction, independent of
# any live LLM call.
#
# The agent's proposed decision must come from its real submit_decision tool
# call — not from re-parsing its closing prose with a second LLM call, which
# is exactly the failure mode this project's own docs (CLAUDE.md) warn
# against: "this is how the decision is captured, not by re-parsing the
# agent's prose with a second LLM call." These tests build synthetic message
# histories (no Bedrock call involved) to pin that behavior down.
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent import _extract_proposed_decision, TOOLS


def test_submit_decision_is_a_real_bound_tool():
    # Regression guard for the actual bug this module fixed: submit_decision
    # existed in tools.py but was never included in the agent's tool list, so
    # it could never actually be called.
    assert "submit_decision" in [t.name for t in TOOLS]


def test_no_submit_decision_call_returns_none():
    messages = [
        HumanMessage(content="Applicant ID: APP-9999"),
        AIMessage(content="I looked into it and it seems fine.", tool_calls=[]),
    ]
    assert _extract_proposed_decision(messages) is None


def test_extracts_decision_and_justification_from_submit_decision_call():
    messages = [
        HumanMessage(content="Applicant ID: APP-9999"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_credit_report", "args": {"applicant_id": "APP-9999"}, "id": "1"}],
        ),
        ToolMessage(content='{"credit_score": 720}', name="get_credit_report", tool_call_id="1"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_decision",
                    "args": {"decision": "approve", "justification": "Strong credit, low DTI."},
                    "id": "2",
                }
            ],
        ),
        ToolMessage(content='{"status": "recorded", "decision": "approve"}', name="submit_decision", tool_call_id="2"),
    ]
    result = _extract_proposed_decision(messages)
    assert result == {"decision": "approve", "justification": "Strong credit, low DTI."}


def test_ignores_tool_calls_other_than_submit_decision():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "calculate_dti", "args": {"monthly_debt": 1000, "annual_income": 60000}, "id": "1"}],
        ),
        ToolMessage(content='{"dti": 0.2}', name="calculate_dti", tool_call_id="1"),
    ]
    assert _extract_proposed_decision(messages) is None
