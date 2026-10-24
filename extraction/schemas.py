# Typed targets for document extraction. The LLM fills these via structured
# output (tool calling), so a response that doesn't fit the schema fails at
# parse time instead of flowing downstream as a half-right dict.
#
# Deliberately NO cross-field consistency rules in here (e.g. gross - deductions
# == net). If a document is internally inconsistent, we want the extracted
# values exactly as the document states them, so validators.py can flag the
# inconsistency and route the document to a human. A model_validator that
# rejected the parse would hide that signal; one that "fixed" it would hide it
# worse.
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["pay_stub", "bank_statement"]


class PayStub(BaseModel):
    employer_name: str
    employee_name: str
    pay_frequency: Literal["weekly", "biweekly", "semimonthly", "monthly"]
    pay_period_start: date
    pay_period_end: date
    pay_date: date
    gross_pay: float = Field(description="Gross earnings for THIS pay period, not year-to-date.")
    total_deductions: float = Field(description="Total of all deductions for this pay period, as a positive number.")
    net_pay: float = Field(description="Net (take-home) pay for this pay period.")
    ytd_gross_pay: float = Field(description="Year-to-date gross earnings.")


class Transaction(BaseModel):
    date: date
    description: str
    amount: float = Field(description="Signed amount: deposits/credits positive, withdrawals/debits negative.")


class BankStatement(BaseModel):
    bank_name: str
    account_holder: str
    account_number_last4: str = Field(description="Last 4 digits of the account number only.", pattern=r"^\d{4}$")
    statement_period_start: date
    statement_period_end: date
    opening_balance: float
    closing_balance: float
    total_deposits: float = Field(description="Total deposits/credits for the period, as a positive number.")
    total_withdrawals: float = Field(description="Total withdrawals/debits for the period, as a positive number.")
    transactions: list[Transaction]


SCHEMAS: dict[str, type[BaseModel]] = {
    "pay_stub": PayStub,
    "bank_statement": BankStatement,
}
