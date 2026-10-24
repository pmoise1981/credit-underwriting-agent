# Generates synthetic pay stubs and bank statements as PDFs, with the ground
# truth kept alongside each one. Entirely fabricated (Faker) — no real PII.
#
# Each document type has three layouts that differ the way real documents do:
# label wording ("Net Pay" vs "Take Home"), date format, money format
# ("(45.00)" vs "-$45.00" vs "45.00-"), where the summary sits, and distractor
# columns (YTD deductions, running balance) that are easy to extract by
# mistake. The point is that one prompt has to cope with all of them, and the
# extraction eval can report accuracy per layout instead of one blended number.
#
# Ground truth is built FIRST as the same Pydantic model the extractor fills,
# then rendered — so "what the document says" and "what the eval expects" can't
# drift apart.
import calendar
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from faker import Faker
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from extraction.schemas import PERIODS_PER_YEAR, BankStatement, DocType, PayStub, Transaction

LAYOUTS = ("classic", "compact", "columns")
YEAR = 2026

_STYLES = getSampleStyleSheet()


# --- formatting variants -----------------------------------------------------

def _money(x: float, layout: str) -> str:
    if layout == "classic":
        return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"
    if layout == "compact":
        return f"({-x:,.2f})" if x < 0 else f"{x:,.2f}"
    return f"{-x:.2f}-" if x < 0 else f"{x:.2f}"  # trailing minus, no separators


_DATE_FORMATS = {"classic": "%m/%d/%Y", "compact": "%b %d, %Y", "columns": "%d %b %Y"}


def _date(d: date, layout: str) -> str:
    return d.strftime(_DATE_FORMATS[layout])


# --- ground truth ------------------------------------------------------------

@dataclass
class PayStubTruth:
    """The extraction target plus the itemized lines the PDF shows (the
    schema only carries the total, the document shows the breakdown)."""
    stub: PayStub
    deductions: list[tuple[str, float]]
    periods_elapsed: int


def make_pay_stub_truth(fake: Faker, rng: random.Random, annual_income: float | None = None,
                        employee_name: str | None = None) -> PayStubTruth:
    freq = rng.choice(list(PERIODS_PER_YEAR))
    annual_income = annual_income or rng.randrange(40_000, 150_000, 500)
    gross = round(annual_income / PERIODS_PER_YEAR[freq], 2)

    month = rng.randint(2, 11)
    if freq == "monthly":
        start, end = date(YEAR, month, 1), date(YEAR, month, calendar.monthrange(YEAR, month)[1])
        elapsed = month
    elif freq == "semimonthly":
        if rng.random() < 0.5:
            start, end, elapsed = date(YEAR, month, 1), date(YEAR, month, 15), 2 * month - 1
        else:
            start, end, elapsed = date(YEAR, month, 16), date(YEAR, month, calendar.monthrange(YEAR, month)[1]), 2 * month
    else:
        length = 7 if freq == "weekly" else 14
        first_start = date(YEAR, 1, 1) + timedelta(days=rng.randint(0, length - 1))
        elapsed = rng.randint(3, 365 // length - 2)
        start = first_start + timedelta(days=length * (elapsed - 1))
        end = start + timedelta(days=length - 1)
    pay_date = end + timedelta(days=rng.randint(0, 5))

    deductions = [
        ("Federal Income Tax", round(gross * rng.uniform(0.09, 0.16), 2)),
        ("State Income Tax", round(gross * rng.uniform(0.03, 0.06), 2)),
        ("Social Security", round(gross * 0.062, 2)),
        ("Medicare", round(gross * 0.0145, 2)),
    ]
    if rng.random() < 0.6:
        deductions.append(("401(k)", round(gross * rng.choice([0.03, 0.04, 0.05, 0.06]), 2)))
    if rng.random() < 0.7:
        deductions.append(("Medical Insurance", round(rng.uniform(40, 180), 2)))
    total = round(sum(a for _, a in deductions), 2)

    stub = PayStub(
        employer_name=fake.company(),
        employee_name=employee_name or fake.name(),
        pay_frequency=freq,
        pay_period_start=start,
        pay_period_end=end,
        pay_date=pay_date,
        gross_pay=gross,
        total_deductions=total,
        net_pay=round(gross - total, 2),
        ytd_gross_pay=round(gross * elapsed, 2),
    )
    return PayStubTruth(stub=stub, deductions=deductions, periods_elapsed=elapsed)


_MERCHANTS = [
    "POS PURCHASE {n} WHOLE FDS MKT", "POS PURCHASE {n} TRADER JOE S", "CHECKCARD {n} SHELL OIL",
    "ACH DEBIT CON ED OF NY", "ACH DEBIT VERIZON WIRELESS", "ONLINE PMT CHASE CARD {n}",
    "ATM WITHDRAWAL #{n}", "AMAZON MKTPLACE PMTS", "NETFLIX.COM", "CVS/PHARMACY #{n}",
    "ZELLE TO {name}", "SPOTIFY USA", "UBER *TRIP",
]


def make_bank_statement_truth(fake: Faker, rng: random.Random, account_holder: str | None = None,
                              payroll_amount: float | None = None) -> BankStatement:
    month = rng.randint(2, 11)
    start, end = date(YEAR, month, 1), date(YEAR, month, calendar.monthrange(YEAR, month)[1])

    def day() -> date:
        return start + timedelta(days=rng.randint(0, (end - start).days))

    payroll = payroll_amount or round(rng.uniform(1_500, 4_500), 2)
    employer = fake.company().upper()
    txns = [
        Transaction(date=start + timedelta(days=rng.randint(0, 3)), description=f"DIRECT DEP {employer} PAYROLL", amount=payroll),
        Transaction(date=start + timedelta(days=rng.randint(14, 17)), description=f"DIRECT DEP {employer} PAYROLL", amount=payroll),
        Transaction(date=start + timedelta(days=rng.randint(0, 4)), description="ACH DEBIT RENT PMT", amount=-round(rng.uniform(1_200, 3_200), 2)),
    ]
    if rng.random() < 0.4:
        txns.append(Transaction(date=day(), description="REFUND AMAZON MKTPLACE", amount=round(rng.uniform(10, 120), 2)))
    for _ in range(rng.randint(10, 22)):
        desc = rng.choice(_MERCHANTS).format(n=rng.randint(1000, 9999), name=fake.first_name().upper())
        amount = -round(rng.choice([rng.uniform(5, 80), rng.uniform(80, 400)]), 2)
        txns.append(Transaction(date=day(), description=desc, amount=amount))
    txns.sort(key=lambda t: t.date)

    opening = round(rng.uniform(1_500, 12_000), 2)
    deposits = round(sum(t.amount for t in txns if t.amount > 0), 2)
    withdrawals = round(-sum(t.amount for t in txns if t.amount < 0), 2)
    return BankStatement(
        bank_name=f"{fake.last_name()} {rng.choice(['National Bank', 'Savings Bank', 'Federal Credit Union', 'Bank & Trust'])}",
        account_holder=account_holder or fake.name(),
        account_number_last4=f"{rng.randint(0, 9999):04d}",
        statement_period_start=start,
        statement_period_end=end,
        opening_balance=opening,
        closing_balance=round(opening + deposits - withdrawals, 2),
        total_deposits=deposits,
        total_withdrawals=withdrawals,
        transactions=txns,
    )


# --- rendering ---------------------------------------------------------------

_GRID = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
])


def _p(text: str, style: str = "Normal") -> Paragraph:
    return Paragraph(text, _STYLES[style])


def _render_pay_stub(t: PayStubTruth, layout: str, fake: Faker) -> list:
    s, m, d = t.stub, (lambda x: _money(x, layout)), (lambda x: _date(x, layout))
    header = [_p(s.employer_name, "Heading2"), _p(fake.address().replace("\n", ", ")), Spacer(1, 8)]
    freq_label = {"weekly": "Weekly", "biweekly": "Bi-Weekly", "semimonthly": "Semi-Monthly", "monthly": "Monthly"}

    if layout == "classic":
        rows = [["Description", "Amount"], ["Gross Pay", m(s.gross_pay)]]
        rows += [[name, m(-amt)] for name, amt in t.deductions]
        rows += [["Total Deductions", m(-s.total_deductions)], ["Net Pay", m(s.net_pay)], ["YTD Gross", m(s.ytd_gross_pay)]]
        return header + [
            _p(f"EARNINGS STATEMENT — {s.employee_name}"),
            _p(f"Pay Period: {d(s.pay_period_start)} - {d(s.pay_period_end)} &nbsp; Pay Date: {d(s.pay_date)}"),
            _p(f"Pay Frequency: {freq_label[s.pay_frequency]}"),
            Spacer(1, 8), Table(rows, style=_GRID),
        ]

    if layout == "compact":
        lines = [
            f"Employee: {s.employee_name}",
            f"Period beginning {d(s.pay_period_start)}, ending {d(s.pay_period_end)}. Check date {d(s.pay_date)}.",
            f"Paid {freq_label[s.pay_frequency].lower()}",
            f"Total Earnings: {m(s.gross_pay)}",
            *[f"&nbsp;&nbsp;{name}: {m(amt)}" for name, amt in t.deductions],
            f"Total Taxes &amp; Deductions: {m(s.total_deductions)}",
            f"Take Home: {m(s.net_pay)}",
            f"Gross Earnings Year to Date: {m(s.ytd_gross_pay)}",
        ]
        return header + [_p(line) for line in lines]

    # columns: current and YTD side by side for every line — the YTD
    # deduction/net columns are distractors the extractor must not pick up.
    n = t.periods_elapsed
    rows = [["", "Current", "Year to Date"], ["GROSS EARNINGS", m(s.gross_pay), m(s.ytd_gross_pay)]]
    rows += [[name.upper(), m(amt), m(round(amt * n, 2))] for name, amt in t.deductions]
    rows += [["TOTAL DEDUCTIONS", m(s.total_deductions), m(round(s.total_deductions * n, 2))],
             ["NET PAY", m(s.net_pay), m(round(s.net_pay * n, 2))]]
    return header + [
        Table([["EMPLOYEE", "PERIOD START", "PERIOD END", "PAY DATE"],
               [s.employee_name, d(s.pay_period_start), d(s.pay_period_end), d(s.pay_date)]], style=_GRID),
        Spacer(1, 8), Table(rows, style=_GRID),
    ]


def _render_bank_statement(s: BankStatement, layout: str, fake: Faker) -> list:
    m, d = (lambda x: _money(x, layout)), (lambda x: _date(x, layout))
    masked = {"classic": f"Account: ****{s.account_number_last4}",
              "compact": f"Account ending in {s.account_number_last4}",
              "columns": f"Acct No. XXXXXXXX{s.account_number_last4}"}[layout]
    header = [_p(s.bank_name, "Heading2"), _p(s.account_holder), _p(fake.address().replace("\n", ", ")),
              _p(masked),
              _p(f"Statement Period: {d(s.statement_period_start)} through {d(s.statement_period_end)}"), Spacer(1, 8)]

    balance = s.opening_balance
    running = []
    for t in s.transactions:
        balance += t.amount
        running.append(balance)

    if layout == "classic":
        summary = Table([["Beginning Balance", m(s.opening_balance)], ["Total Deposits", m(s.total_deposits)],
                         ["Total Withdrawals", m(-s.total_withdrawals)], ["Ending Balance", m(s.closing_balance)]],
                        style=_GRID)
        rows = [["Date", "Description", "Amount", "Balance"]]
        rows += [[d(t.date), t.description, m(t.amount), m(b)] for t, b in zip(s.transactions, running)]
        return header + [summary, Spacer(1, 8), Table(rows, style=_GRID, repeatRows=1)]

    if layout == "compact":
        summary = [_p(f"Previous balance {m(s.opening_balance)} &nbsp; Credits {m(s.total_deposits)} &nbsp; "
                      f"Debits {m(s.total_withdrawals)} &nbsp; New balance {m(s.closing_balance)}")]
        rows = [["Posted", "Transaction", "Amount"]]
        rows += [[d(t.date), t.description, m(t.amount)] for t in s.transactions]
        return header + summary + [Spacer(1, 8), Table(rows, style=_GRID, repeatRows=1)]

    # columns: separate withdrawal/deposit columns (sign is carried by the
    # column, not the number), running balance, and the summary at the END.
    rows = [["DATE", "DESCRIPTION", "WITHDRAWALS", "DEPOSITS", "BALANCE"],
            ["", "OPENING BALANCE", "", "", m(s.opening_balance)]]
    rows += [[d(t.date), t.description, m(-t.amount) if t.amount < 0 else "", m(t.amount) if t.amount > 0 else "", m(b)]
             for t, b in zip(s.transactions, running)]
    footer = Table([["TOTAL WITHDRAWALS", m(s.total_withdrawals)], ["TOTAL DEPOSITS", m(s.total_deposits)],
                    ["CLOSING BALANCE", m(s.closing_balance)]], style=_GRID)
    return header + [Table(rows, style=_GRID, repeatRows=1), Spacer(1, 8), footer]


def render_pdf(path: Path, flowables: list) -> None:
    # invariant=1 pins the PDF's timestamps/IDs so the same seed gives the
    # same bytes.
    SimpleDocTemplate(str(path), pagesize=letter, invariant=1).build(flowables)


# --- corpus ------------------------------------------------------------------

@dataclass
class SynthDoc:
    doc_id: str
    doc_type: DocType
    layout: str
    pdf_path: Path
    truth: BaseModel


def generate_corpus(out_dir: str | Path, docs_per_layout: int = 4, seed: int = 0) -> list[SynthDoc]:
    """Writes docs_per_layout PDFs for every (doc_type, layout) pair into
    out_dir, plus manifest.jsonl holding each document's ground truth."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for doc_type in ("pay_stub", "bank_statement"):
        for layout in LAYOUTS:
            for i in range(docs_per_layout):
                doc_id = f"{doc_type}-{layout}-{i:02d}"
                rng = random.Random(f"{seed}:{doc_id}")
                fake = Faker()
                fake.seed_instance(f"{seed}:{doc_id}")
                if doc_type == "pay_stub":
                    t = make_pay_stub_truth(fake, rng)
                    truth, flowables = t.stub, _render_pay_stub(t, layout, fake)
                else:
                    truth = make_bank_statement_truth(fake, rng)
                    flowables = _render_bank_statement(truth, layout, fake)
                pdf_path = out_dir / f"{doc_id}.pdf"
                render_pdf(pdf_path, flowables)
                docs.append(SynthDoc(doc_id, doc_type, layout, pdf_path, truth))

    with open(out_dir / "manifest.jsonl", "w") as f:
        for doc in docs:
            f.write(json.dumps({"doc_id": doc.doc_id, "doc_type": doc.doc_type, "layout": doc.layout,
                                "pdf": doc.pdf_path.name, "truth": doc.truth.model_dump(mode="json")}) + "\n")
    return docs


def make_applicant_documents(out_dir: str | Path, seed_key: str, applicant_name: str,
                             documented_annual_income: float, stub_layout: str, bank_layout: str,
                             tamper_pay_stub: bool = False) -> dict[str, SynthDoc]:
    """Renders one applicant's pay stub + bank statement. Everything except the
    name is driven by seed_key, so two applicants given the same seed_key get
    identical documents apart from the name — which the fair lending eval
    relies on for its mirrored pairs.

    tamper_pay_stub raises the stated net pay after the fact, the way an edited
    stub would look: the stub no longer adds up, and no bank deposit matches it.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed_key)
    fake = Faker()
    fake.seed_instance(seed_key)

    t = make_pay_stub_truth(fake, rng, annual_income=documented_annual_income, employee_name=applicant_name)
    deposited = t.stub.net_pay
    if tamper_pay_stub:
        t.stub = t.stub.model_copy(update={"net_pay": round(t.stub.net_pay + 250, 2)})
    stmt = make_bank_statement_truth(fake, rng, account_holder=applicant_name, payroll_amount=deposited)

    docs = {
        "pay_stub": SynthDoc("pay_stub", "pay_stub", stub_layout, out_dir / "pay_stub.pdf", t.stub),
        "bank_statement": SynthDoc("bank_statement", "bank_statement", bank_layout, out_dir / "bank_statement.pdf", stmt),
    }
    render_pdf(docs["pay_stub"].pdf_path, _render_pay_stub(t, stub_layout, fake))
    render_pdf(docs["bank_statement"].pdf_path, _render_bank_statement(stmt, bank_layout, fake))
    return docs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a synthetic financial-document corpus.")
    parser.add_argument("--out", default="extraction/sample_docs")
    parser.add_argument("--per-layout", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    corpus = generate_corpus(args.out, args.per_layout, args.seed)
    print(f"Wrote {len(corpus)} documents + manifest.jsonl to {args.out}")
