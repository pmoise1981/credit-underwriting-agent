# The underwriting agent. Uses LangGraph's prebuilt create_react_agent so the
# LLM itself decides which tools to call and in what order (genuinely agentic,
# unlike the fixed classify->retrieve->generate pipeline in the RAG project).
#
# After the agent proposes a decision, a SEPARATE deterministic step (guardrails.py)
# has final say — the agent's proposal is a recommendation, not an authorization.
from typing import Literal
import uuid
import json
from decimal import Decimal
from datetime import datetime, timezone

import boto3
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from config import llm, AWS_REGION, DECISIONS_TABLE
from tools import get_applicant_profile, get_credit_report, calculate_dti
from guardrails import enforce_guardrails

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


def _floats_to_decimal(obj):
    """DynamoDB's put_item rejects native Python floats — only Decimal is
    accepted. Converts recursively before persisting the audit record."""
    if isinstance(obj, list):
        return [_floats_to_decimal(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


TOOLS = [get_applicant_profile, get_credit_report, calculate_dti]
react_agent = create_react_agent(llm, tools=TOOLS)

SYSTEM_INSTRUCTION = (
    "You are a loan underwriting assistant. Given an applicant ID, investigate the case: "
    "fetch the applicant's profile, fetch their credit report, and calculate their DTI ratio. "
    "Then propose ONE recommendation: 'approve', 'decline', or 'escalate' (for cases needing human "
    "judgment), with a one-paragraph justification. You are making a RECOMMENDATION only — a separate "
    "policy layer has final authority and may override you."
)


class ProposedDecision(BaseModel):
    decision: Literal["approve", "decline", "escalate"] = Field(description="The agent's recommended decision")
    justification: str = Field(description="One-paragraph reasoning for the recommendation")


decision_extractor = llm.with_structured_output(ProposedDecision)


def _extract_tool_log_and_facts(messages) -> tuple[list[dict], dict]:
    """Pulls the tool-call sequence (for audit) and the key numeric facts
    (loan_amount, dti, credit_score) out of the agent's message history —
    reading real tool outputs rather than trusting the agent's prose summary.
    Tool outputs are clean JSON (tools.py strips Decimal types), so json.loads
    parses reliably here."""
    tool_log = []
    facts = {"loan_amount": None, "dti": None, "credit_score": None}

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_log.append({"tool": msg.name, "output": str(msg.content)})
            content = str(msg.content).replace("'", '"')  # tolerate either quoting style
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                continue

            if msg.name == "get_applicant_profile" and "loan_amount_requested" in parsed:
                facts["loan_amount"] = parsed.get("loan_amount_requested")
            if msg.name == "get_credit_report" and "credit_score" in parsed:
                facts["credit_score"] = parsed.get("credit_score")
            if msg.name == "calculate_dti" and "dti" in parsed:
                facts["dti"] = parsed.get("dti")

    return tool_log, facts


def run_case(applicant_id: str) -> dict:
    """Runs one underwriting case end-to-end: agent investigation -> proposed
    decision -> deterministic guardrail enforcement -> final audited result."""
    case_id = str(uuid.uuid4())

    result = react_agent.invoke({
        "messages": [HumanMessage(content=f"{SYSTEM_INSTRUCTION}\n\nApplicant ID: {applicant_id}")]
    })
    messages = result["messages"]
    final_text = messages[-1].content

    tool_log, facts = _extract_tool_log_and_facts(messages)
    proposed = decision_extractor.invoke(f"Extract the recommendation from this analysis:\n\n{final_text}")

    if None in facts.values():
        guardrail_result = {
            "final_decision": "escalate",
            "guardrail_triggered": True,
            "reason": f"Incomplete investigation — missing facts: {[k for k, v in facts.items() if v is None]}",
        }
    else:
        guardrail_result = enforce_guardrails(
            proposed_decision=proposed.decision,
            loan_amount=facts["loan_amount"],
            dti=facts["dti"],
            credit_score=facts["credit_score"],
        )

    case_record = {
        "case_id": case_id,
        "applicant_id": applicant_id,
        "tool_calls": tool_log,
        "extracted_facts": facts,
        "proposed_decision": proposed.decision,
        "proposed_justification": proposed.justification,
        "final_decision": guardrail_result["final_decision"],
        "guardrail_triggered": guardrail_result["guardrail_triggered"],
        "guardrail_reason": guardrail_result["reason"],
    }

    try:
        table = _dynamodb.Table(DECISIONS_TABLE)
        table.put_item(Item=_floats_to_decimal({**case_record, "timestamp": datetime.now(timezone.utc).isoformat()}))
    except Exception as e:  # noqa: BLE001 — audit logging must never crash the actual decision
        case_record["audit_log_error"] = str(e)

    return case_record
