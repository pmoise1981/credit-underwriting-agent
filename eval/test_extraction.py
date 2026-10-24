# Deterministic tests for the extraction layer — no LLM calls. They pin down
# the parts the live eval (eval_extraction.py) relies on but can't check itself:
# that synthetic ground truth is internally consistent, that the PDFs actually
# contain the values they claim to, that validators.py catches each kind of
# corruption it is meant to, and that the eval's scoring counts errors right.
import os
import sys
from datetime import timedelta

import pytest
from langchain_core.runnables import RunnableLambda

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_extraction import score_document
from extraction.extractor import extract_document, pdf_to_text
from extraction.schemas import BankStatement, PayStub
from extraction.synth import generate_corpus
from extraction.validators import validate_document


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return generate_corpus(tmp_path_factory.mktemp("corpus"), docs_per_layout=3, seed=123)


def _first(corpus, cls):
    return next(d for d in corpus if isinstance(d.truth, cls))


# --- synthetic corpus --------------------------------------------------------

def test_ground_truth_passes_validators(corpus):
    for doc in corpus:
        assert validate_document(doc.truth) == [], doc.doc_id


def test_pdfs_contain_ground_truth_values(corpus):
    for doc in corpus:
        text = pdf_to_text(doc.pdf_path).replace(",", "").replace("$", "")
        t = doc.truth
        expected = ([t.gross_pay, t.net_pay, t.ytd_gross_pay] if isinstance(t, PayStub)
                    else [t.opening_balance, t.closing_balance] + [abs(x.amount) for x in t.transactions])
        for value in expected:
            assert f"{value:.2f}" in text, f"{doc.doc_id}: {value:.2f} not rendered"


def test_corpus_is_deterministic(tmp_path):
    a = generate_corpus(tmp_path / "a", docs_per_layout=1, seed=7)
    b = generate_corpus(tmp_path / "b", docs_per_layout=1, seed=7)
    assert [d.truth for d in a] == [d.truth for d in b]
    assert all(x.pdf_path.read_bytes() == y.pdf_path.read_bytes() for x, y in zip(a, b))


# --- validators catch each corruption ---------------------------------------

def test_pay_stub_corruptions_are_flagged(corpus):
    stub = _first(corpus, PayStub).truth
    corruptions = {
        "misread net": {"net_pay": stub.net_pay + 1},
        "ytd picked as current": {"gross_pay": stub.ytd_gross_pay + 1},
        "negative deductions": {"total_deductions": -stub.total_deductions,
                                "net_pay": stub.gross_pay + stub.total_deductions},
        "dates swapped": {"pay_period_start": stub.pay_period_end, "pay_period_end": stub.pay_period_start},
    }
    for name, change in corruptions.items():
        assert validate_document(stub.model_copy(update=change)), name


def test_bank_statement_corruptions_are_flagged(corpus):
    stmt = _first(corpus, BankStatement).truth
    txns = stmt.transactions
    flipped = [txns[0].model_copy(update={"amount": -txns[0].amount})] + txns[1:]
    shifted = [txns[0].model_copy(update={"date": stmt.statement_period_end + timedelta(days=1)})] + txns[1:]
    corruptions = {
        "dropped transaction": {"transactions": txns[1:]},
        "duplicated transaction": {"transactions": txns + [txns[-1]]},
        "sign flip": {"transactions": flipped},
        "misread closing balance": {"closing_balance": stmt.closing_balance + 10},
        "transaction outside period": {"transactions": shifted},
    }
    for name, change in corruptions.items():
        assert validate_document(stmt.model_copy(update=change)), name


# --- extractor plumbing (stub LLM) -------------------------------------------

class _StubLLM:
    def __init__(self, response):
        self.response, self.seen = response, None

    def with_structured_output(self, schema):
        def respond(messages):
            self.seen = messages
            return self.response
        return RunnableLambda(respond)


def test_extractor_sends_pdf_text_and_returns_model(corpus):
    doc = _first(corpus, PayStub)
    llm = _StubLLM(doc.truth)
    assert extract_document(doc.pdf_path, "pay_stub", llm=llm) == doc.truth
    assert doc.truth.employee_name in llm.seen[-1].content


def test_extractor_rejects_wrong_output_type(corpus):
    doc = _first(corpus, PayStub)
    with pytest.raises(ValueError):
        extract_document(doc.pdf_path, "pay_stub", llm=_StubLLM({"not": "a model"}))


# --- eval scoring ------------------------------------------------------------

def test_scoring(corpus):
    stmt = _first(corpus, BankStatement).truth
    assert score_document(stmt, stmt)["fully_correct"]

    wrong_name = score_document(stmt, stmt.model_copy(update={"bank_name": "Other Bank"}))
    assert not wrong_name["fully_correct"]
    assert wrong_name["fields"]["bank_name"] is False

    dropped = score_document(stmt, stmt.model_copy(update={"transactions": stmt.transactions[1:]}))
    assert dropped["txn_precision"] == 1.0 and dropped["txn_recall"] < 1.0
    assert not dropped["fully_correct"]

    t0 = stmt.transactions[0]
    misdescribed = stmt.model_copy(update={
        "transactions": [t0.model_copy(update={"description": "SOMETHING ELSE"})] + stmt.transactions[1:]})
    wrong_desc = score_document(stmt, misdescribed)
    assert wrong_desc["txn_precision"] == 1.0 and wrong_desc["txn_recall"] == 1.0
    assert wrong_desc["txn_description_accuracy"] < 1.0
    assert not wrong_desc["fully_correct"]

    reformatted = stmt.model_copy(update={
        "transactions": [t0.model_copy(update={"description": "  " + t0.description.lower()})] + stmt.transactions[1:]})
    assert score_document(stmt, reformatted)["fully_correct"]

    failed = score_document(stmt, None)
    assert not any(failed["fields"].values()) and failed["txn_recall"] == 0.0


@pytest.mark.parametrize("raw, expected", [
    ("Bi-Weekly", "biweekly"), ("every 2 weeks", "biweekly"), ("Semi-Monthly", "semimonthly"),
    ("twice a month", "semimonthly"), ("WEEKLY", "weekly"), ("monthly", "monthly"),
])
def test_pay_frequency_spellings_normalize(corpus, raw, expected):
    stub = _first(corpus, PayStub).truth.model_dump()
    assert PayStub(**{**stub, "pay_frequency": raw}).pay_frequency == expected


def test_unknown_pay_frequency_still_rejected(corpus):
    stub = _first(corpus, PayStub).truth.model_dump()
    with pytest.raises(ValueError):
        PayStub(**{**stub, "pay_frequency": "quarterly"})
