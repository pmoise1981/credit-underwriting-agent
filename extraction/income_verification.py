# Verifies an applicant's income from their documents: extract each one,
# validate it on its own (validators.py), then cross-check the documents
# against the application and against each other. All checks after extraction
# are plain Python.
#
# Output is a recommendation input, not a decision: guardrails.py decides what
# a failed verification or an income gap means for auto-approval.
from pathlib import Path

from extraction.extractor import extract_document
from extraction.schemas import PERIODS_PER_YEAR, BankStatement, PayStub
from extraction.validators import money_eq, validate_document


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def verify_income(applicant_name: str, documents: dict[str, Path], llm=None) -> dict:
    """Returns {"verified_annual_income": float | None, "verification_passed": bool,
    "issues": [str], "documents": {doc_type: summary}}.

    verified_annual_income is the pay stub's current gross annualized by pay
    frequency; it is reported even when other checks fail (so the size of a
    gap is visible), and is None only when no pay stub could be extracted.
    """
    issues = []
    extracted = {}
    for doc_type in ("pay_stub", "bank_statement"):
        path = documents.get(doc_type)
        if path is None:
            issues.append(f"no {doc_type} on file")
            continue
        try:
            doc = extract_document(path, doc_type, llm=llm)
        except Exception as e:  # noqa: BLE001 — an unreadable document is a verification failure, not a crash
            issues.append(f"{doc_type}: extraction failed ({type(e).__name__})")
            continue
        extracted[doc_type] = doc
        issues += [f"{doc_type}: {v}" for v in validate_document(doc)]

    stub: PayStub | None = extracted.get("pay_stub")
    stmt: BankStatement | None = extracted.get("bank_statement")
    if stub and not _same_name(stub.employee_name, applicant_name):
        issues.append(f"pay stub employee '{stub.employee_name}' does not match applicant '{applicant_name}'")
    if stmt and not _same_name(stmt.account_holder, applicant_name):
        issues.append(f"bank account holder '{stmt.account_holder}' does not match applicant '{applicant_name}'")
    # A genuine pay stub's net pay lands in the applicant's account; an edited
    # or fabricated one usually doesn't.
    if stub and stmt and not any(t.amount > 0 and money_eq(t.amount, stub.net_pay) for t in stmt.transactions):
        issues.append(f"no bank deposit matches pay stub net pay {stub.net_pay:.2f}")

    verified = round(stub.gross_pay * PERIODS_PER_YEAR[stub.pay_frequency], 2) if stub else None
    summaries = {}
    if stub:
        summaries["pay_stub"] = stub.model_dump(mode="json")
    if stmt:
        # Totals only — the transaction list is long and the checks above
        # already used it.
        summaries["bank_statement"] = stmt.model_dump(mode="json", exclude={"transactions"})
    return {
        "verified_annual_income": verified,
        "verification_passed": not issues and verified is not None,
        "issues": issues,
        "documents": summaries,
    }
