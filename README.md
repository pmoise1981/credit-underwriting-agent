# Credit Underwriting Agent

A genuinely agentic system (the LLM decides which tools to call and when — not a fixed pipeline) that investigates loan applications, proposes a decision, and is subject to a deterministic guardrail layer that can override an unsafe recommendation. Backed by an **automated evaluation suite that runs in CI on every push**, gating merges on agent safety and quality regressions.

All applicant and credit data is **synthetic** — fabricated for demonstration, no real PII.

## Why this is different from a RAG project

A RAG system answers questions from retrieved text. This system **takes actions with consequences** — it investigates a real case and recommends approve/decline/escalate. That's a different, harder governance problem: a bad retrieval gives a bad answer; a bad agent decision could authorize a loan that shouldn't be authorized. The guardrail layer exists specifically to make that failure mode structurally impossible, not just unlikely.

## Architecture

```
Applicant ID -> [ReAct Agent: LangGraph]
                    |-- decides which tools to call, in what order
                    |-- get_applicant_profile
                    |-- get_credit_report
                    |-- calculate_dti
                    -> proposes: approve / decline / escalate
                            |
                            v
                [Deterministic Guardrail Layer] <- NOT an LLM
                    |-- hard policy thresholds (loan amount, DTI, credit score)
                    |-- can OVERRIDE an "approve" proposal -> forces "escalate"
                            |
                            v
                    Final decision + full audit trail -> DynamoDB
```

**The core guardrail property**: the agent's proposal is a *recommendation*, not an authorization. `guardrails.py` runs after the agent, reads the actual extracted numbers (not the agent's prose), and can force any unsafe "approve" into "escalate" — the agent cannot reason its way around this because it's plain Python, not a prompt instruction.

## The automated eval (the actual point of this project)

`eval/eval_agentic.py` is built to run in CI (`.github/workflows/eval.yml`), not by hand. On every push:

1. **Tool-call completeness** — did the agent actually investigate (call every required tool), or guess from partial information?
2. **Guardrail compliance (zero tolerance)** — for cases that must never be auto-approved, was "approve" ever the final decision anyway? A single failure here fails the build outright, independent of every other score.
3. **Decision accuracy** — for cases with an unambiguous expected outcome, does the agent's final decision match?

The workflow exits non-zero on any failure, which GitHub can enforce as a required check — blocking a regression from merging, the same way a unit-test failure would.

## Project structure

```
config.py           # model, AWS settings, hard policy thresholds
tools.py              # tools the agent can call (data lookups, calculations only — no decisions)
guardrails.py           # deterministic override layer, separate from the agent
agent.py                  # the LangGraph ReAct agent + fact extraction + guardrail enforcement
data_seed.py                # synthetic applicant/credit data
main.py                        # local CLI entry point
lambda_handler.py                 # AWS Lambda entry point
eval/eval_dataset.py                 # golden cases with expected safety properties
eval/eval_agentic.py                    # the CI-gating eval harness
.github/workflows/eval.yml                 # runs the eval suite on every push/PR
terraform/                                     # DynamoDB, Lambda, IAM, ECR — all as code
```

## Running it

```bash
pip install -r requirements.txt
python data_seed.py    # seed synthetic applicants/credit reports into DynamoDB
python main.py          # run one case
python eval/eval_agentic.py   # run the full eval suite locally
```

Full AWS deploy:
```bash
./deploy.sh
```

## Setting up the CI gate

The GitHub Actions workflow needs AWS credentials as repository secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) with permission to call Bedrock and DynamoDB — evals that invoke a real LLM need real credentials, this can't be mocked away entirely. Once set, go to the repo's branch protection settings and mark "Agent Evaluation" as a required status check to actually enforce the gate on pull requests.

## What's not implemented

- No real credit bureau integration (synthetic data only)
- No document verification (income docs, ID verification)
- No formal model validation of the underlying LLM's decision quality beyond this eval suite (e.g., no fairness/bias testing across protected classes — a real production system would need this)
- Guardrail thresholds ($50k, 43% DTI, 680 credit score) are illustrative, not derived from a specific institution's actual policy

## Proof it actually works

### The guardrail override, on tape

A live request to the deployed Lambda for an applicant with excellent credit (780), low DTI (15.4%), and a strong income ($140k) - but a $75,000 loan request, over the $50,000 auto-approve ceiling.

The agent's own reasoning concluded "approve" with a detailed justification citing every positive signal in the file. The guardrail layer overrode it anyway, purely on the dollar amount:

> "final_decision": "escalate", "guardrail_triggered": true, "guardrail_reason": "Agent proposed auto-approval, but hard policy limit(s) require human review: loan amount $75,000 >= $50,000 auto-approve ceiling"

This is the actual point of the project: the agent can build a compelling case for an unsafe action, and the deterministic layer stops it anyway - not because the model chose to comply, but because it structurally cannot bypass the check.

![Guardrail override transcript](docs/screenshots/guardrail-override-transcript.png)

### Automated eval running in CI, not just locally

The eval suite runs automatically via GitHub Actions on every push - not a script that has to be remembered and run by hand.

![CI workflow passing](docs/screenshots/ci-workflow-passing.png)
![CI job steps](docs/screenshots/ci-job-steps.png)

Eval output from inside the CI run itself: Tool-call completeness 1.00, Decision accuracy 1.00, Guardrail failures 0 (zero tolerance threshold) - PASS, all thresholds met.

![CI eval log output](docs/screenshots/ci-eval-log-output.png)
