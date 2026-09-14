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
# many eval cases back-to-back in CI). max_attempts was raised from 10 to 25
# after a real CI run exhausted 10 attempts under adaptive backoff and still
# hit ThrottlingException — see EVAL_CALL_PACING_SECONDS below, which reduces
# how often retries are needed in the first place. Neither fully eliminates
# throttling if the account's actual Bedrock on-demand throughput is the
# bottleneck — that requires a quota increase on the AWS side, not a retry
# policy change.
BEDROCK_RETRY_CONFIG = Config(retries={"max_attempts": 25, "mode": "adaptive"})

# --- Pacing between sequential eval-suite calls to the same Bedrock account,
# to keep well under its on-demand rate limit instead of relying on retries
# to absorb a burst after the fact. Override via env var if a given account's
# quota allows tighter (or needs looser) pacing. ---
EVAL_CALL_PACING_SECONDS = float(os.environ.get("EVAL_CALL_PACING_SECONDS", "4"))

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
