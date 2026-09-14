# Central settings, shared model client, and hard policy thresholds.
# The thresholds here are the actual guardrail values enforced in guardrails.py —
# kept in config, not scattered through the agent, so the policy is auditable
# in one place.
import os
from botocore.config import Config
from langchain_aws import ChatBedrockConverse

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# --- DynamoDB table names (synthetic mock data only — no real PII/applicant data) ---
APPLICANTS_TABLE = "underwriting-agent-applicants"
CREDIT_REPORTS_TABLE = "underwriting-agent-credit-reports"
DECISIONS_TABLE = "underwriting-agent-decisions"  # audit log of every case the agent processed

# --- Retry config: absorbs Bedrock throttling under burst load (e.g. running
# many eval cases back-to-back in CI) ---
BEDROCK_RETRY_CONFIG = Config(retries={"max_attempts": 10, "mode": "adaptive"})

# --- LLM ---
llm = ChatBedrockConverse(
    model="us.anthropic.claude-sonnet-4-6",
    region_name=AWS_REGION,
    temperature=0,
    config=BEDROCK_RETRY_CONFIG,
)

# --- Hard policy thresholds (deterministic guardrails, not LLM judgment) ---
# Any loan amount at or above this MUST be escalated to a human, regardless of
# what the agent's own reasoning concludes. This is enforced in guardrails.py,
# not by asking the model nicely — see README for why that distinction matters.
# These values are illustrative placeholders for demonstration purposes -- they
# are NOT sourced from any specific institution actual underwriting policy.
# A real deployment would replace these with the institution actual credit
# box, approved by risk/compliance, not hardcoded constants in application code.
#
AUTO_APPROVE_MAX_AMOUNT = 50_000
MAX_DTI_FOR_AUTO_APPROVE = 0.43  # standard qualified-mortgage DTI ceiling
MIN_CREDIT_SCORE_FOR_AUTO_APPROVE = 680
