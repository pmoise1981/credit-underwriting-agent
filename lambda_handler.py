# AWS Lambda entry point — same agent, deployed as a container image.
import json
from agent import run_case


def handler(event, context):
    body = json.loads(event.get("body") or "{}")
    applicant_id = body.get("applicant_id")

    if not applicant_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing 'applicant_id' in request body"})}

    result = run_case(applicant_id)
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(result)}
