# Extraction eval: generates a fresh synthetic corpus (seeded, so every run
# sees the same documents), extracts each PDF with the real LLM, and scores the
# result against ground truth.
#
# Scored per document:
#   1. Field accuracy — every scalar field, broken down by doc type, layout and
#      field, so "the columns layout misreads YTD" is visible instead of being
#      averaged away.
#   2. Transaction precision/recall — bank statements only, matched on
#      (date, amount) as a multiset, so a dropped or duplicated line counts.
#   3. Silent error rate (the one that matters most) — documents that were
#      extracted WRONG and still passed validators.py. A wrong-but-flagged
#      document goes to a human and costs time; a wrong-and-unflagged one
#      flows into an underwriting decision. Also reports the false-alarm rate
#      (correct extraction flagged anyway) since a validator that flags
#      everything would score zero silent errors and be useless.
#
# Thresholds below are a first cut, not a measured baseline — tighten them
# once a few CI runs show where the model actually lands.
import csv
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extraction.extractor import extract_document
from extraction.schemas import BankStatement
from extraction.synth import generate_corpus
from extraction.validators import validate_document

FIELD_ACCURACY_THRESHOLD = 0.95
TRANSACTION_F1_THRESHOLD = 0.95
SILENT_ERROR_RATE_THRESHOLD = 0.05

DOCS_PER_LAYOUT = int(os.environ.get("EXTRACTION_DOCS_PER_LAYOUT", "4"))
# Pacing between Bedrock calls — see CLAUDE.md, adaptive retry alone has not
# been enough under batch load.
PACING_SECONDS = float(os.environ.get("EXTRACTION_PACING_SECONDS", "2"))


def _values_match(expected, actual) -> bool:
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(expected, actual, abs_tol=0.005)
    if isinstance(expected, str):
        return isinstance(actual, str) and " ".join(expected.split()).casefold() == " ".join(actual.split()).casefold()
    return expected == actual


def score_document(truth, extracted) -> dict:
    """Compares one extraction to ground truth. extracted=None means the
    extraction failed outright, which scores as every field wrong."""
    field_results = {
        name: extracted is not None and _values_match(getattr(truth, name), getattr(extracted, name))
        for name in type(truth).model_fields
        if name != "transactions"
    }
    score = {"fields": field_results, "txn_precision": None, "txn_recall": None}

    if isinstance(truth, BankStatement):
        expected = Counter((t.date, round(t.amount, 2)) for t in truth.transactions)
        got = Counter((t.date, round(t.amount, 2)) for t in extracted.transactions) if extracted else Counter()
        matched = sum((expected & got).values())
        score["txn_precision"] = matched / sum(got.values()) if got else 0.0
        score["txn_recall"] = matched / sum(expected.values())

    score["fully_correct"] = all(field_results.values()) and score["txn_recall"] in (None, 1.0) \
        and score["txn_precision"] in (None, 1.0)
    return score


def _f1(p, r):
    return 2 * p * r / (p + r) if p + r else 0.0


def _log_run_history(entry: dict):
    history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_history.jsonl")
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        git_sha = os.environ.get("GITHUB_SHA", "unknown")[:7]
    entry = {"eval": "document_extraction", "timestamp": datetime.now(timezone.utc).isoformat(),
             "git_sha": git_sha, **entry}
    with open(history_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_eval():
    rows = []
    field_hits = defaultdict(list)  # (doc_type, layout, field) -> [bool]

    with tempfile.TemporaryDirectory() as tmp:
        corpus = generate_corpus(tmp, docs_per_layout=DOCS_PER_LAYOUT)
        for i, doc in enumerate(corpus):
            if i:
                time.sleep(PACING_SECONDS)
            print(f"Extracting {doc.doc_id}")
            error = None
            try:
                extracted = extract_document(doc.pdf_path, doc.doc_type)
                violations = validate_document(extracted)
            except Exception as e:  # noqa: BLE001 — a failed extraction is a scored outcome, not a crash
                extracted, violations, error = None, ["extraction failed"], f"{type(e).__name__}: {e}"

            score = score_document(doc.truth, extracted)
            for field, ok in score["fields"].items():
                field_hits[(doc.doc_type, doc.layout, field)].append(ok)
            flagged = bool(violations)
            rows.append({
                "doc_id": doc.doc_id,
                "doc_type": doc.doc_type,
                "layout": doc.layout,
                "field_accuracy": sum(score["fields"].values()) / len(score["fields"]),
                "wrong_fields": ";".join(f for f, ok in score["fields"].items() if not ok),
                "txn_precision": score["txn_precision"],
                "txn_recall": score["txn_recall"],
                "fully_correct": score["fully_correct"],
                "flagged_by_validator": flagged,
                "silent_error": not score["fully_correct"] and not flagged,
                "false_alarm": score["fully_correct"] and flagged,
                "violations": " | ".join(violations),
                "error": error,
            })

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extraction_results.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    all_hits = [ok for hits in field_hits.values() for ok in hits]
    field_accuracy = sum(all_hits) / len(all_hits)
    bank_rows = [r for r in rows if r["txn_recall"] is not None]
    txn_p = sum(r["txn_precision"] for r in bank_rows) / len(bank_rows)
    txn_r = sum(r["txn_recall"] for r in bank_rows) / len(bank_rows)
    txn_f1 = _f1(txn_p, txn_r)
    silent_rate = sum(r["silent_error"] for r in rows) / len(rows)
    false_alarm_rate = sum(r["false_alarm"] for r in rows) / len(rows)

    print("\n=== Field accuracy by doc type / layout ===")
    by_layout = defaultdict(list)
    for (doc_type, layout, _), hits in field_hits.items():
        by_layout[(doc_type, layout)] += hits
    for (doc_type, layout), hits in sorted(by_layout.items()):
        print(f"  {doc_type:15s} {layout:8s} {sum(hits) / len(hits):.3f}")
    weak = [(k, sum(h) / len(h)) for k, h in field_hits.items() if sum(h) < len(h)]
    if weak:
        print("\n  Fields below 100%:")
        for (doc_type, layout, field), acc in sorted(weak, key=lambda x: x[1]):
            print(f"    {doc_type}/{layout}/{field}: {acc:.2f}")

    print("\n=== Eval Summary ===")
    print(f"Documents:              {len(rows)}")
    print(f"Field accuracy:         {field_accuracy:.3f} (threshold: {FIELD_ACCURACY_THRESHOLD})")
    print(f"Transaction P / R / F1: {txn_p:.3f} / {txn_r:.3f} / {txn_f1:.3f} (F1 threshold: {TRANSACTION_F1_THRESHOLD})")
    print(f"Silent error rate:      {silent_rate:.3f} (threshold: {SILENT_ERROR_RATE_THRESHOLD})")
    print(f"False alarm rate:       {false_alarm_rate:.3f} (reported, not gated)")

    _log_run_history({"documents": len(rows), "field_accuracy": field_accuracy, "txn_f1": txn_f1,
                      "silent_error_rate": silent_rate, "false_alarm_rate": false_alarm_rate})

    failed = False
    if silent_rate > SILENT_ERROR_RATE_THRESHOLD:
        print("\nFAIL: too many wrong extractions passed validation unflagged.")
        failed = True
    if field_accuracy < FIELD_ACCURACY_THRESHOLD:
        print("\nFAIL: field accuracy below threshold.")
        failed = True
    if txn_f1 < TRANSACTION_F1_THRESHOLD:
        print("\nFAIL: transaction F1 below threshold.")
        failed = True

    if failed:
        sys.exit(1)
    print("\nPASS: all thresholds met.")
    sys.exit(0)


if __name__ == "__main__":
    run_eval()
