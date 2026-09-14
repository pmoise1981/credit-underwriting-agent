# CLAUDE.md — project context for AI coding assistants

## What this is

A LangGraph ReAct agent that investigates loan applications and recommends
approve/decline/escalate, with a deterministic (non-LLM) guardrail layer that
can override an unsafe "approve" regardless of the agent's own reasoning.
Includes two automated CI-gated evals: agent safety/correctness, and fair
lending disparity testing (Four-Fifths Rule).

All applicant/credit data is synthetic. No real PII.

## Architecture (read these files in this order to understand the system)

1. `config.py` — model client, DynamoDB table names, hard policy thresholds
   (these are illustrative placeholders, not a real institution's policy —
   see the comment directly above them).
2. `tools.py` — data-lookup tools + `submit_decision`. Tools return
   `json.dumps(...)` strings explicitly — never rely on default
   stringification of a dict, that was a real bug once (fragile parsing
   downstream). `get_applicant_profile` strips `demographic_group` before
   returning — the agent must never see this field.
3. `guardrails.py` — plain Python, not a prompt. Runs AFTER the agent
   proposes a decision and can override "approve" into "escalate". This
   is the actual safety property of the whole system: the agent's proposal
   is a recommendation, not an authorization.
4. `agent.py` — the LangGraph ReAct loop. The agent's final action MUST be
   calling `submit_decision` (a real tool call) — this is how the decision
   is captured, not by re-parsing the agent's prose with a second LLM call.
   `_extract_case_details` walks the message history once to build the
   audit log, the extracted facts, and the proposed decision together.
5. `data_seed.py` — synthetic applicants/credit reports. Group A and Group B
   applicants use IDENTICAL income/debt/credit distributions by design, so
   any approval-rate gap in the fairness eval is attributable to the agent,
   not to the two groups having different underlying risk profiles.
6. `eval/eval_agentic.py` — safety/correctness eval. Zero-tolerance gate on
   guardrail compliance; threshold-based on tool completeness and decision
   accuracy. Exits non-zero to fail CI.
7. `eval/fair_lending_eval.py` — Four-Fifths Rule disparity test. Has a hard
   minimum-sample-size gate (`MIN_SAMPLE_SIZE_PER_GROUP`) — fails loudly
   rather than reporting a falsely-precise ratio on too few cases. Supports
   `EVAL_N_REPEATS` env var to check run-to-run decision stability (LLM
   outputs are not perfectly deterministic even at temperature=0).
8. `.github/workflows/eval.yml` — runs both evals on every push to `master`
   (this repo's default branch — NOT `main`, check before assuming).

## Known gotchas — read before touching Bedrock calls

- **Bedrock throttling under batch load.** Running many cases back-to-back
  (e.g., the fair lending eval's 28+ cases, especially with `N_REPEATS>1`)
  can exceed on-demand rate limits, even with `BEDROCK_RETRY_CONFIG`'s
  adaptive retry. If you see `ThrottlingException`, add `time.sleep()`
  pacing inside the loop (already present in `fair_lending_eval.py` —
  don't remove it during a rewrite, that regression already happened once).
- **Full-file rewrites lose small fixes if you're not careful.** When
  regenerating a file from scratch (e.g. via a heredoc), diff against what
  was actually working before — a full rewrite silently dropped the
  `time.sleep()` pacing call once and reintroduced a throttling failure.
- **Terminal quoting with apostrophes.** Any inline Python string containing
  a contraction (agent's, institution's) breaks nested shell quoting badly
  in a WSL bash session. Prefer `sed` inserts or a temp `.py` script written
  via `create_file`-equivalent over nested `python3 -c "..."` string
  replacement when the target string has an apostrophe.
- **`__pycache__` and Terraform's `.terraform/` provider binaries are huge.**
  Both have caused failed/rejected pushes in this project family (GitHub's
  100MB file limit). `.gitignore` should already cover both — check it's
  present before the first commit in a fresh clone.

## Running things

```bash
pip install -r requirements.txt
python data_seed.py                    # seed synthetic data into DynamoDB
python main.py                          # run one case locally
python eval/eval_agentic.py               # safety/correctness eval
python eval/fair_lending_eval.py             # fairness eval (set EVAL_N_REPEATS=N for stability check)
./deploy.sh                                   # full AWS deploy (Terraform + Docker + Lambda)
```

## What NOT to do

- Never let the guardrail layer's logic move into a prompt instruction — the
  entire point of `guardrails.py` is that it's plain Python the LLM cannot
  reason around. Any "fix" that moves a hard limit into `SYSTEM_INSTRUCTION`
  instead of `guardrails.py` defeats the actual safety property being
  demonstrated.
- Never let `get_applicant_profile` return `demographic_group` to the agent.
  The fairness eval's validity depends on the agent genuinely not having
  access to that field.
- Don't treat a single fairness eval run (`EVAL_N_REPEATS=1`, the CI default)
  as a validated result — it's a point estimate. A real stability claim
  requires `EVAL_N_REPEATS>1` and checking `stable_across_repeats` in the
  output.
