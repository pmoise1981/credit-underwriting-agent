# Seeds DynamoDB with entirely synthetic applicant and credit-report data.
# None of this is real PII or real credit data — every name, SSN-shaped ID, and
# figure below is fabricated for demonstration purposes only.
import boto3
from config import AWS_REGION, APPLICANTS_TABLE, CREDIT_REPORTS_TABLE

SYNTHETIC_APPLICANTS = [
    {
        "applicant_id": "APP-1001",
        "name": "Jordan Test-Applicant-A",
        "annual_income": 85000,
        "monthly_debt": 1200,
        "loan_amount_requested": 25000,
        "loan_purpose": "auto",
    },
    {
        "applicant_id": "APP-1002",
        "name": "Sam Test-Applicant-B",
        "annual_income": 62000,
        "monthly_debt": 2100,
        "loan_amount_requested": 45000,
        "loan_purpose": "debt_consolidation",
    },
    {
        "applicant_id": "APP-1003",
        "name": "Casey Test-Applicant-C",
        "annual_income": 140000,
        "monthly_debt": 1800,
        "loan_amount_requested": 75000,
        "loan_purpose": "home_improvement",
    },
    {
        "applicant_id": "APP-1004",
        "name": "Riley Test-Applicant-D",
        "annual_income": 40000,
        "monthly_debt": 1900,
        "loan_amount_requested": 15000,
        "loan_purpose": "personal",
    },
]

SYNTHETIC_CREDIT_REPORTS = [
    {"applicant_id": "APP-1001", "credit_score": 720, "delinquencies_24mo": 0, "open_accounts": 6},
    {"applicant_id": "APP-1002", "credit_score": 660, "delinquencies_24mo": 1, "open_accounts": 9},
    {"applicant_id": "APP-1003", "credit_score": 780, "delinquencies_24mo": 0, "open_accounts": 5},
    {"applicant_id": "APP-1004", "credit_score": 590, "delinquencies_24mo": 3, "open_accounts": 11},
]


def seed():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    applicants = dynamodb.Table(APPLICANTS_TABLE)
    credit_reports = dynamodb.Table(CREDIT_REPORTS_TABLE)

    for item in SYNTHETIC_APPLICANTS:
        applicants.put_item(Item=item)
    for item in SYNTHETIC_CREDIT_REPORTS:
        credit_reports.put_item(Item=item)

    print(f"Seeded {len(SYNTHETIC_APPLICANTS)} applicants and {len(SYNTHETIC_CREDIT_REPORTS)} credit reports.")


if __name__ == "__main__":
    seed()
