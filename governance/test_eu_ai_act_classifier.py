# Real classification cases, including this repo's own Credit Underwriting
# Agent as a worked example of Annex III high-risk classification - deployed
# in the EU, it would be a creditworthiness-scoring system, which is exactly
# the category Annex III(5)(b) names. That's the point of building this
# tool instead of just reading about risk tiers: applying it to a system you
# already know inside out is the fastest way to actually understand where
# the boundaries are.
from governance.eu_ai_act_classifier import (
    AISystemDescription,
    RiskTier,
    SystemTag,
    classify,
)


def test_credit_underwriting_agent_is_high_risk():
    """This repo's own agent, described honestly, lands squarely in Annex
    III(5)(b) - the exact provision covering creditworthiness evaluation
    and credit scoring."""
    system = AISystemDescription(
        name="Credit Underwriting Agent",
        purpose="Investigates loan applications and recommends approve/decline/escalate",
        deployer_type="private_entity",
        tags=[SystemTag.CREDIT_SCORING_CREDITWORTHINESS],
    )
    result = classify(system)
    assert result.tier is RiskTier.HIGH
    assert result.matched_tag is SystemTag.CREDIT_SCORING_CREDITWORTHINESS
    assert "Annex III(5)(b)" in result.citation
    assert "Conformity assessment before deployment (Article 43)" in result.obligations
    assert "Human oversight designed in, not bolted on (Article 14)" in result.obligations


def test_prohibited_practice_overrides_everything_else():
    """A system tagged with both a prohibited practice AND a high-risk
    category still comes back unacceptable - Article 5 wins outright,
    there's no such thing as 'mostly fine.'"""
    system = AISystemDescription(
        name="Hypothetical hiring + social-scoring tool",
        purpose="Screens job candidates and also scores citizens for a public benefits agency",
        deployer_type="public_authority",
        tags=[
            SystemTag.EMPLOYMENT_WORKER_MANAGEMENT,
            SystemTag.SOCIAL_SCORING_PUBLIC_AUTHORITY,
        ],
    )
    result = classify(system)
    assert result.tier is RiskTier.UNACCEPTABLE
    assert result.matched_tag is SystemTag.SOCIAL_SCORING_PUBLIC_AUTHORITY
    assert result.obligations == [
        (
            "None - the system may not be deployed; redesign to remove the "
            "prohibited capability, there is no compliance path that keeps it."
        )
    ]


def test_consumer_chatbot_is_limited_risk_transparency_only():
    system = AISystemDescription(
        name="Customer support chatbot",
        purpose="Answers customer billing questions on a retail website",
        deployer_type="private_entity",
        tags=[SystemTag.CHATBOT_DIRECT_CONSUMER_INTERACTION],
    )
    result = classify(system)
    assert result.tier is RiskTier.LIMITED
    assert result.obligations == [
        (
            "Disclose to the natural person that they are interacting with or viewing "
            "AI-generated/manipulated content."
        )
    ]


def test_no_matching_tags_is_minimal_risk():
    system = AISystemDescription(
        name="Internal spam filter",
        purpose="Filters spam out of an internal email inbox",
        deployer_type="private_entity",
        tags=[],
    )
    result = classify(system)
    assert result.tier is RiskTier.MINIMAL
    assert result.matched_tag is None
    assert result.obligations == []


def test_high_risk_tag_ignored_once_prohibited_tag_already_matched_first_in_list_order():
    """Order in the tags list shouldn't matter - Article 5 is checked as a
    full pass over all tags before Annex III is checked at all."""
    system = AISystemDescription(
        name="Order-independence check",
        purpose="Same two tags as the override test, reversed order",
        deployer_type="public_authority",
        tags=[
            SystemTag.SOCIAL_SCORING_PUBLIC_AUTHORITY,
            SystemTag.EMPLOYMENT_WORKER_MANAGEMENT,
        ],
    )
    result = classify(system)
    assert result.tier is RiskTier.UNACCEPTABLE
