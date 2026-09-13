# Tools available to the underwriting agent. Data-lookup tools return JSON
# strings explicitly (json.dumps) — never relying on default stringification —
# so downstream parsing is a plain json.loads with no quote-replacement
# heuristics, regardless of what characters appear in the underlying data.
from typing import Literal
from decimal import Decimal
import json

import boto3
from langchain_core.tools import tool
from config import AWS_REGION, APPLICANTS_TABLE, CREDIT_REPORTS_TABLE

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


def _clean_decimals(obj):
    """DynamoDB returns numbers as Decimal — convert to plain int/float before
    JSON-serializing (json.dumps can't handle Decimal directly)."""
    if isinstance(obj, list):
        return [_clean_decimals(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _clean_decimals(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


@tool
def get_applicant_profile(applicant_id: str) -> str:
    """Fetches the applicant's stated income, debt, and loan request details."""
    table = _dynamodb.Table(APPLICANTS_TABLE)
    response = table.get_item(Key={"applicant_id": applicant_id})
    item = response.get("Item", {"error": f"No applicant found for {applicant_id}"})
    item = _clean_decimals(item)
    item.pop("demographic_group", None)  # never expose protected-class field to the agent itself
    return json.dumps(item)


@tool
def get_credit_report(applicant_id: str) -> str:
    """Fetches the applicant's credit score, delinquency history, and open account count."""
    table = _dynamodb.Table(CREDIT_REPORTS_TABLE)
    response = table.get_item(Key={"applicant_id": applicant_id})
    item = response.get("Item", {"error": f"No credit report found for {applicant_id}"})
    return json.dumps(_clean_decimals(item))


@tool
def calculate_dti(monthly_debt: float, annual_income: float) -> str:
    """Calculates debt-to-income ratio given monthly debt payments and annual income."""
    if annual_income <= 0:
        return json.dumps({"error": "annual_income must be positive"})
    monthly_income = annual_income / 12
    dti = round(monthly_debt / monthly_income, 4)
    return json.dumps({"dti": dti, "monthly_income": round(monthly_income, 2)})


@tool
def submit_decision(decision: Literal["approve", "decline", "escalate"], justification: str) -> str:
    """Call this EXACTLY ONCE, as your final action, to submit your underwriting
    recommendation. This IS the decision — do not just describe your recommendation
    in prose, you must call this tool."""
    return json.dumps({"status": "recorded", "decision": decision})
