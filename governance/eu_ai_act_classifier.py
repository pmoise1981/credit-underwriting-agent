# EU AI Act risk-tier classifier. Rules-based, not ML — the Act itself defines
# risk by category and use case, not by measuring a system's behavior, so a
# classifier for it is a lookup against those categories, not a model.
#
# Applies the Act's real structure: Article 5 prohibited practices ->
# unacceptable risk (cannot be placed on the market, full stop). Annex III
# use-case categories -> high-risk (conformity assessment, technical
# documentation, human oversight, risk management, logging, EU database
# registration). Article 50 -> limited risk (disclosure obligation only).
# Everything else -> minimal risk, effectively unregulated by the Act.
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SystemTag(StrEnum):
    """Controlled vocabulary of AI use cases the Act treats specially.
    Real systems combine several of these; classification runs Article 5
    first because a prohibited practice overrides everything else regardless
    of what other tags are also present."""

    # --- Article 5: prohibited practices (unacceptable risk) ---
    SUBLIMINAL_MANIPULATION = "subliminal_manipulation"
    EXPLOITING_VULNERABILITIES = "exploiting_vulnerabilities"
    SOCIAL_SCORING_PUBLIC_AUTHORITY = "social_scoring_public_authority"
    REALTIME_REMOTE_BIOMETRIC_ID_LAW_ENFORCEMENT = "realtime_remote_biometric_id_law_enforcement"
    BIOMETRIC_CATEGORIZATION_SENSITIVE_ATTRIBUTES = "biometric_categorization_sensitive_attributes"
    EMOTION_RECOGNITION_WORKPLACE_EDUCATION = "emotion_recognition_workplace_education"
    PREDICTIVE_POLICING_PROFILING_ONLY = "predictive_policing_profiling_only"
    UNTARGETED_FACIAL_RECOGNITION_SCRAPING = "untargeted_facial_recognition_scraping"

    # --- Annex III: high-risk use-case categories ---
    BIOMETRIC_IDENTIFICATION_VERIFICATION = "biometric_identification_verification"
    CRITICAL_INFRASTRUCTURE_SAFETY_COMPONENT = "critical_infrastructure_safety_component"
    EDUCATION_ACCESS_OR_SCORING = "education_access_or_scoring"
    EMPLOYMENT_WORKER_MANAGEMENT = "employment_worker_management"
    CREDIT_SCORING_CREDITWORTHINESS = "credit_scoring_creditworthiness"
    ESSENTIAL_SERVICES_ELIGIBILITY = "essential_services_eligibility"
    LAW_ENFORCEMENT_RISK_ASSESSMENT = "law_enforcement_risk_assessment"
    MIGRATION_ASYLUM_BORDER_CONTROL = "migration_asylum_border_control"
    ADMINISTRATION_OF_JUSTICE_DEMOCRATIC_PROCESSES = "administration_of_justice_democratic_processes"

    # --- Article 50: transparency-only obligations (limited risk) ---
    CHATBOT_DIRECT_CONSUMER_INTERACTION = "chatbot_direct_consumer_interaction"
    DEEPFAKE_CONTENT_GENERATION = "deepfake_content_generation"
    AI_GENERATED_PUBLIC_INTEREST_TEXT = "ai_generated_public_interest_text"


class RiskTier(StrEnum):
    UNACCEPTABLE = "unacceptable"
    HIGH = "high"
    LIMITED = "limited"
    MINIMAL = "minimal"


class AISystemDescription(BaseModel):
    """What you'd actually know about a system before deploying it - this is
    the input a real intake/governance-review form would collect."""

    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1, description="Plain-language description of what it does")
    deployer_type: Literal["public_authority", "private_entity"]
    tags: list[SystemTag] = Field(default_factory=list)


class Classification(BaseModel):
    system_name: str
    tier: RiskTier
    matched_tag: SystemTag | None
    citation: str
    rationale: str
    obligations: list[str]


_PROHIBITED_CITATIONS: dict[SystemTag, str] = {
    SystemTag.SUBLIMINAL_MANIPULATION: "Article 5(1)(a) - subliminal techniques distorting behavior",
    SystemTag.EXPLOITING_VULNERABILITIES: "Article 5(1)(b) - exploiting age/disability/socioeconomic vulnerability",
    SystemTag.SOCIAL_SCORING_PUBLIC_AUTHORITY: "Article 5(1)(c) - social scoring by public authorities",
    SystemTag.REALTIME_REMOTE_BIOMETRIC_ID_LAW_ENFORCEMENT: (
        "Article 5(1)(h) - real-time remote biometric ID in public spaces for law "
        "enforcement (narrow statutory exceptions exist; treat as prohibited by default)"
    ),
    SystemTag.BIOMETRIC_CATEGORIZATION_SENSITIVE_ATTRIBUTES: (
        "Article 5(1)(g) - biometric categorization inferring race, political opinion, "
        "religion, sexual orientation, etc."
    ),
    SystemTag.EMOTION_RECOGNITION_WORKPLACE_EDUCATION: (
        "Article 5(1)(f) - emotion recognition in the workplace or education, absent a "
        "narrow medical/safety exception"
    ),
    SystemTag.PREDICTIVE_POLICING_PROFILING_ONLY: (
        "Article 5(1)(d) - predictive policing based solely on profiling, with no "
        "objective, verifiable facts"
    ),
    SystemTag.UNTARGETED_FACIAL_RECOGNITION_SCRAPING: (
        "Article 5(1)(e) - untargeted scraping of facial images to build/expand a "
        "recognition database"
    ),
}

_HIGH_RISK_CITATIONS: dict[SystemTag, str] = {
    SystemTag.BIOMETRIC_IDENTIFICATION_VERIFICATION: "Annex III(1) - biometric identification/verification",
    SystemTag.CRITICAL_INFRASTRUCTURE_SAFETY_COMPONENT: "Annex III(2) - safety component in critical infrastructure",
    SystemTag.EDUCATION_ACCESS_OR_SCORING: "Annex III(3) - access to, or scoring within, education/vocational training",
    SystemTag.EMPLOYMENT_WORKER_MANAGEMENT: "Annex III(4) - recruitment, task allocation, performance/conduct monitoring",
    SystemTag.CREDIT_SCORING_CREDITWORTHINESS: "Annex III(5)(b) - creditworthiness evaluation and credit scoring",
    SystemTag.ESSENTIAL_SERVICES_ELIGIBILITY: "Annex III(5) - eligibility for essential public/private services",
    SystemTag.LAW_ENFORCEMENT_RISK_ASSESSMENT: "Annex III(6) - risk assessment in law enforcement",
    SystemTag.MIGRATION_ASYLUM_BORDER_CONTROL: "Annex III(7) - migration, asylum, and border control management",
    SystemTag.ADMINISTRATION_OF_JUSTICE_DEMOCRATIC_PROCESSES: (
        "Annex III(8) - administration of justice and democratic processes"
    ),
}

_TRANSPARENCY_CITATIONS: dict[SystemTag, str] = {
    SystemTag.CHATBOT_DIRECT_CONSUMER_INTERACTION: "Article 50(1) - must disclose the user is interacting with AI",
    SystemTag.DEEPFAKE_CONTENT_GENERATION: "Article 50(4) - must disclose content is AI-generated/manipulated",
    SystemTag.AI_GENERATED_PUBLIC_INTEREST_TEXT: (
        "Article 50(4) - must disclose AI-generated text on matters of public interest"
    ),
}

_HIGH_RISK_OBLIGATIONS = [
    "Risk management system across the full lifecycle (Article 9)",
    "Data governance - training/validation/test data quality and representativeness (Article 10)",
    "Technical documentation before market placement (Article 11, Annex IV)",
    "Automatic logging/record-keeping for traceability (Article 12)",
    "Transparency and instructions for use enabling deployer compliance (Article 13)",
    "Human oversight designed in, not bolted on (Article 14)",
    "Accuracy, robustness, and cybersecurity appropriate to the use case (Article 15)",
    "Conformity assessment before deployment (Article 43)",
    "Registration in the EU high-risk AI system database (Article 71)",
]

_LIMITED_RISK_OBLIGATION = "Disclose to the natural person that they are interacting with or viewing AI-generated/manipulated content."


def classify(system: AISystemDescription) -> Classification:
    """Article 5 is checked first and wins outright: a prohibited practice
    makes every other tag irrelevant - there's no such thing as a system
    that's 'high-risk but also fine because it's mostly a chatbot'."""
    for tag in system.tags:
        if tag in _PROHIBITED_CITATIONS:
            return Classification(
                system_name=system.name,
                tier=RiskTier.UNACCEPTABLE,
                matched_tag=tag,
                citation=_PROHIBITED_CITATIONS[tag],
                rationale=(
                    f"{system.name} matches a prohibited practice under {_PROHIBITED_CITATIONS[tag]}. "
                    "This system cannot be placed on the market or put into service in the EU "
                    "in this form, regardless of any other characteristics."
                ),
                obligations=[
                    (
                        "None - the system may not be deployed; redesign to remove the "
                        "prohibited capability, there is no compliance path that keeps it."
                    )
                ],
            )

    for tag in system.tags:
        if tag in _HIGH_RISK_CITATIONS:
            return Classification(
                system_name=system.name,
                tier=RiskTier.HIGH,
                matched_tag=tag,
                citation=_HIGH_RISK_CITATIONS[tag],
                rationale=(
                    f"{system.name} falls under {_HIGH_RISK_CITATIONS[tag]}. High-risk status "
                    "follows from the use case itself, not from how well or badly the system "
                    "happens to perform."
                ),
                obligations=list(_HIGH_RISK_OBLIGATIONS),
            )

    for tag in system.tags:
        if tag in _TRANSPARENCY_CITATIONS:
            return Classification(
                system_name=system.name,
                tier=RiskTier.LIMITED,
                matched_tag=tag,
                citation=_TRANSPARENCY_CITATIONS[tag],
                rationale=(
                    f"{system.name} triggers a transparency-only obligation under "
                    f"{_TRANSPARENCY_CITATIONS[tag]} - no conformity assessment or risk "
                    "management system is required, just disclosure."
                ),
                obligations=[_LIMITED_RISK_OBLIGATION],
            )

    return Classification(
        system_name=system.name,
        tier=RiskTier.MINIMAL,
        matched_tag=None,
        citation="No Article 5, Annex III, or Article 50 category matched",
        rationale=(
            f"{system.name} does not match a prohibited practice, a high-risk Annex III "
            "category, or an Article 50 transparency trigger, based on the tags provided. "
            "The Act does not impose binding obligations at this tier - voluntary codes of "
            "conduct (Article 95) are the only applicable mechanism."
        ),
        obligations=[],
    )
