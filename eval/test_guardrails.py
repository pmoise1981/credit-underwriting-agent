# Deterministic unit tests for guardrails.py, independent of the LLM agent.
#
# eval_agentic.py only checks the *final* decision on live agent runs — if the
# nondeterministic agent happens to never propose "approve" on an unsafe case,
# that eval would pass even if enforce_guardrails() itself were broken and
# could no longer override an approval. These tests call enforce_guardrails()
# directly with a forced "approve" proposal for each threshold violation, so a
# regression here fails immediately and deterministically, with no agent call
# involved.
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guardrails import enforce_guardrails
from config import AUTO_APPROVE_MAX_AMOUNT, MAX_DTI_FOR_AUTO_APPROVE, MIN_CREDIT_SCORE_FOR_AUTO_APPROVE

SAFE = {
    "loan_amount": AUTO_APPROVE_MAX_AMOUNT - 1000,
    "dti": MAX_DTI_FOR_AUTO_APPROVE - 0.01,
    "credit_score": MIN_CREDIT_SCORE_FOR_AUTO_APPROVE + 10,
}


def test_approve_stands_when_no_threshold_violated():
    result = enforce_guardrails(proposed_decision="approve", **SAFE)
    assert result["final_decision"] == "approve"
    assert result["guardrail_triggered"] is False


def test_loan_amount_at_ceiling_overrides_approve():
    result = enforce_guardrails(proposed_decision="approve", **{**SAFE, "loan_amount": AUTO_APPROVE_MAX_AMOUNT})
    assert result["final_decision"] != "approve"
    assert result["guardrail_triggered"] is True


def test_dti_over_ceiling_overrides_approve():
    result = enforce_guardrails(proposed_decision="approve", **{**SAFE, "dti": MAX_DTI_FOR_AUTO_APPROVE + 0.01})
    assert result["final_decision"] != "approve"
    assert result["guardrail_triggered"] is True


def test_credit_score_below_floor_overrides_approve():
    result = enforce_guardrails(
        proposed_decision="approve", **{**SAFE, "credit_score": MIN_CREDIT_SCORE_FOR_AUTO_APPROVE - 1}
    )
    assert result["final_decision"] != "approve"
    assert result["guardrail_triggered"] is True


def test_multiple_violations_still_override_approve():
    result = enforce_guardrails(proposed_decision="approve", loan_amount=AUTO_APPROVE_MAX_AMOUNT * 2, dti=0.9, credit_score=500)
    assert result["final_decision"] != "approve"
    assert result["guardrail_triggered"] is True


def test_violation_without_approve_proposal_is_not_overridden():
    # The guardrail only overrides an "approve" proposal — a "decline" or
    # "escalate" proposal is already not an auto-approval, so it stands as-is
    # even when a threshold is violated.
    result = enforce_guardrails(proposed_decision="decline", **{**SAFE, "credit_score": 500})
    assert result["final_decision"] == "decline"
    assert result["guardrail_triggered"] is False
