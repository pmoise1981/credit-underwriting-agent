# The underwriting agent. Uses LangGraph's prebuilt create_react_agent so the
# LLM itself decides which tools to call and in what order (genuinely agentic,
# unlike the fixed classify->retrieve->generate pipeline in the RAG project).
#
# After the agent proposes a decision, a SEPARATE deterministic step (guardrails.py)
# has final say — the agent's proposal is a recommendation, not an authorization.
import uuid
import json
from decimal import Decimal
from datetime import datetime, timezone

import boto3
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from config import llm, AWS_REGION, DECISIONS_TABLE
from tools import get_applicant_profile, get_credit_report, calculate_dti, submit_decision
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


TOOLS = [get_applicant_profile, get_credit_report, calculate_dti, submit_decision]
react_agent = create_react_agent(llm, tools=TOOLS)

SYSTEM_INSTRUCTION = (
    "You are a loan underwriting assistant. Given an applicant ID, investigate the case: "
    "fetch the applicant's profile, fetch their credit report, and calculate their DTI ratio. "
    "Then call submit_decision, exactly once, as your final action, with ONE recommendation — "
    "'approve', 'decline', or 'escalate' (for cases needing human judgment) — and a one-paragraph "
    "justification. Calling submit_decision IS how you submit your recommendation; do not just "
    "describe it in prose. You are making a RECOMMENDATION only — a separate policy layer has final "
    "authority and may override you."
)


def _extract_proposed_decision(messages) -> dict | None:
    """Finds the agent's submit_decision call and returns its arguments. This
    reads the actual tool call the agent made — the real final action — rather
    than re-parsing the agent's closing prose with a second LLM call, which is
    fragile and not what the agent actually committed to as its action."""
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls or []:
                if call["name"] == "submit_decision":
                    return {"decision": call["args"]["decision"], "justification": call["args"]["justification"]}
    return None


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

    tool_log, facts = _extract_tool_log_and_facts(messages)
    proposed = _extract_proposed_decision(messages)

    if proposed is None:
        guardrail_result = {
            "final_decision": "escalate",
            "guardrail_triggered": True,
            "reason": "Incomplete investigation — agent never called submit_decision.",
        }
    elif None in facts.values():
        guardrail_result = {
            "final_decision": "escalate",
            "guardrail_triggered": True,
            "reason": f"Incomplete investigation — missing facts: {[k for k, v in facts.items() if v is None]}",
        }
    else:
        guardrail_result = enforce_guardrails(
            proposed_decision=proposed["decision"],
            loan_amount=facts["loan_amount"],
            dti=facts["dti"],
            credit_score=facts["credit_score"],
        )

    case_record = {
        "case_id": case_id,
        "applicant_id": applicant_id,
        "tool_calls": tool_log,
        "extracted_facts": facts,
        "proposed_decision": proposed["decision"] if proposed else None,
        "proposed_justification": proposed["justification"] if proposed else None,
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
