# Tools available to the underwriting agent. Each tool does ONE thing — fetch
# data or compute a number — and returns it. None of these tools makes a
# decision; decision logic lives in guardrails.py and the agent's own reasoning,
# kept separate so every step is individually auditable.
from decimal import Decimal

import boto3
from langchain_core.tools import tool
from config import AWS_REGION, APPLICANTS_TABLE, CREDIT_REPORTS_TABLE

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)


def _clean_decimals(obj):
    """DynamoDB returns numbers as Decimal, which isn't valid JSON/Python-literal
    syntax when stringified (e.g. Decimal('85000')) — convert to plain int/float
    so tool outputs round-trip cleanly through JSON parsing downstream."""
    if isinstance(obj, list):
        return [_clean_decimals(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _clean_decimals(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


@tool
def get_applicant_profile(applicant_id: str) -> dict:
    """Fetches the applicant's stated income, debt, and loan request details."""
    table = _dynamodb.Table(APPLICANTS_TABLE)
    response = table.get_item(Key={"applicant_id": applicant_id})
    item = response.get("Item", {"error": f"No applicant found for {applicant_id}"})
    item = _clean_decimals(item)
    item.pop("demographic_group", None)  # never expose protected-class field to the agent itself
    return item


@tool
def get_credit_report(applicant_id: str) -> dict:
    """Fetches the applicant's credit score, delinquency history, and open account count."""
    table = _dynamodb.Table(CREDIT_REPORTS_TABLE)
    response = table.get_item(Key={"applicant_id": applicant_id})
    item = response.get("Item", {"error": f"No credit report found for {applicant_id}"})
    return _clean_decimals(item)


@tool
def calculate_dti(monthly_debt: float, annual_income: float) -> dict:
    """Calculates debt-to-income ratio given monthly debt payments and annual income."""
    if annual_income <= 0:
        return {"error": "annual_income must be positive"}
    monthly_income = annual_income / 12
    dti = round(monthly_debt / monthly_income, 4)
    return {"dti": dti, "monthly_income": round(monthly_income, 2)}
