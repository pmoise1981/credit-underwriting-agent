# Deterministic guardrail enforcement. This is plain Python, not a prompt
# instruction — the agent cannot reason its way around these checks because
# they run AFTER the agent's proposed decision and can override it outright.
# This mirrors the pattern from the other project's validation testing:
# "deterministic enforcement beats model self-restraint."
from config import AUTO_APPROVE_MAX_AMOUNT, MAX_DTI_FOR_AUTO_APPROVE, MIN_CREDIT_SCORE_FOR_AUTO_APPROVE


def enforce_guardrails(proposed_decision: str, loan_amount: float, dti: float, credit_score: int) -> dict:
    """Takes the agent's proposed decision and the underlying numbers, and
    returns the FINAL decision after applying hard policy limits. The agent's
    proposal is only honored if it doesn't violate any hard limit below.

    Returns: {"final_decision": str, "guardrail_triggered": bool, "reason": str}
    """
    violations = []

    if loan_amount >= AUTO_APPROVE_MAX_AMOUNT:
        violations.append(f"loan amount ${loan_amount:,.0f} >= ${AUTO_APPROVE_MAX_AMOUNT:,.0f} auto-approve ceiling")

    if dti > MAX_DTI_FOR_AUTO_APPROVE:
        violations.append(f"DTI {dti:.2%} exceeds {MAX_DTI_FOR_AUTO_APPROVE:.0%} auto-approve ceiling")

    if credit_score < MIN_CREDIT_SCORE_FOR_AUTO_APPROVE:
        violations.append(f"credit score {credit_score} below {MIN_CREDIT_SCORE_FOR_AUTO_APPROVE} auto-approve floor")

    if proposed_decision == "approve" and violations:
        # The agent wanted to auto-approve, but a hard limit says no — override it.
        return {
            "final_decision": "escalate",
            "guardrail_triggered": True,
            "reason": "Agent proposed auto-approval, but hard policy limit(s) require human review: "
            + "; ".join(violations),
        }

    return {
        "final_decision": proposed_decision,
        "guardrail_triggered": False,
        "reason": "No hard limits violated; agent's proposed decision stands.",
    }
