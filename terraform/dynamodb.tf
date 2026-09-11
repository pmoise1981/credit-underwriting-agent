resource "aws_dynamodb_table" "applicants" {
  name         = "underwriting-agent-applicants"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "applicant_id"

  attribute {
    name = "applicant_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "credit_reports" {
  name         = "underwriting-agent-credit-reports"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "applicant_id"

  attribute {
    name = "applicant_id"
    type = "S"
  }
}

# Audit trail — every case the agent processes, including its proposed decision,
# the guardrail's final decision, and whether the guardrail overrode the agent.
resource "aws_dynamodb_table" "decisions" {
  name         = "underwriting-agent-decisions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "case_id"

  attribute {
    name = "case_id"
    type = "S"
  }
}
