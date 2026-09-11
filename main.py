# Local entry point — run one underwriting case from the command line.
import json
from agent import run_case

if __name__ == "__main__":
    result = run_case("APP-1002")  # a case designed to trip the DTI/loan-amount guardrails — see eval_dataset.py
    print(json.dumps(result, indent=2))
