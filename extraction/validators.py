# Deterministic consistency checks on extracted documents. Same principle as
# guardrails.py: plain Python the LLM cannot reason around. A document that
# fails any check is not passed to the underwriting agent as-is — it goes to a
# human, because either the extraction is wrong or the document itself is
# (both are reasons not to auto-decide on it).
#
# These catch arithmetic-visible errors only (a misread amount, a dropped or
# duplicated transaction, a sign flip). They cannot catch a wrong value that
# happens to stay consistent, e.g. a misspelled employer name — that's what the
# extraction eval measures separately.
import math

from pydantic import BaseModel

from extraction.schemas import BankStatement, PayStub

# Half a cent: amounts are rounded to cents on the document, so any real
# discrepancy is at least 0.01.
MONEY_TOLERANCE = 0.005


def _money_eq(a: float, b: float) -> bool:
    return math.isclose(a, b, abs_tol=MONEY_TOLERANCE)


def validate_pay_stub(stub: PayStub) -> list[str]:
    violations = []
    if not stub.pay_period_start <= stub.pay_period_end <= stub.pay_date:
        violations.append(
            f"date order: period {stub.pay_period_start}..{stub.pay_period_end}, paid {stub.pay_date}"
        )
    if not _money_eq(stub.gross_pay - stub.total_deductions, stub.net_pay):
        violations.append(
            f"gross {stub.gross_pay:.2f} - deductions {stub.total_deductions:.2f} != net {stub.net_pay:.2f}"
        )
    if min(stub.gross_pay, stub.total_deductions, stub.net_pay) < 0:
        violations.append("negative gross, deductions, or net pay")
    if stub.ytd_gross_pay + MONEY_TOLERANCE < stub.gross_pay:
        violations.append(f"YTD gross {stub.ytd_gross_pay:.2f} < period gross {stub.gross_pay:.2f}")
    return violations


def validate_bank_statement(stmt: BankStatement) -> list[str]:
    violations = []
    if stmt.statement_period_start > stmt.statement_period_end:
        violations.append(f"period start {stmt.statement_period_start} after end {stmt.statement_period_end}")

    outside = [t for t in stmt.transactions if not stmt.statement_period_start <= t.date <= stmt.statement_period_end]
    if outside:
        violations.append(f"{len(outside)} transaction(s) dated outside the statement period")

    net = sum(t.amount for t in stmt.transactions)
    if not _money_eq(stmt.opening_balance + net, stmt.closing_balance):
        violations.append(
            f"opening {stmt.opening_balance:.2f} + transactions {net:.2f} != closing {stmt.closing_balance:.2f}"
        )

    deposits = sum(t.amount for t in stmt.transactions if t.amount > 0)
    if not _money_eq(deposits, stmt.total_deposits):
        violations.append(f"sum of deposits {deposits:.2f} != stated total {stmt.total_deposits:.2f}")

    withdrawals = -sum(t.amount for t in stmt.transactions if t.amount < 0)
    if not _money_eq(withdrawals, stmt.total_withdrawals):
        violations.append(f"sum of withdrawals {withdrawals:.2f} != stated total {stmt.total_withdrawals:.2f}")
    return violations


def validate_document(doc: BaseModel) -> list[str]:
    """Returns a list of human-readable violations; empty means the document
    is internally consistent."""
    if isinstance(doc, PayStub):
        return validate_pay_stub(doc)
    if isinstance(doc, BankStatement):
        return validate_bank_statement(doc)
    raise TypeError(f"no validator for {type(doc).__name__}")
