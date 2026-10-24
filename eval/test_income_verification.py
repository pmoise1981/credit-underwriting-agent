# Deterministic tests for document-based income verification — no LLM calls.
# A stub LLM returns each document's ground truth, so these test what happens
# AFTER extraction: per-document validation, cross-document checks, and the
# annualized income. Extraction accuracy itself is eval_extraction.py's job.
import os
import sys

import pytest
from langchain_core.runnables import RunnableLambda

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_seed import DOCUMENT_SPECS, MIRRORED_APPLICANTS, SYNTHETIC_APPLICANTS
from extraction.income_verification import verify_income
from extraction.synth import make_applicant_documents

NAMES = {a["applicant_id"]: a["name"] for a in SYNTHETIC_APPLICANTS}


class _TruthLLM:
    """Stands in for Bedrock: 'extracts' each document perfectly."""

    def __init__(self, docs, fail=False):
        self.truths = {type(d.truth): d.truth for d in docs.values()}
        self.fail = fail

    def with_structured_output(self, schema):
        def respond(_messages):
            if self.fail:
                raise ValueError("unparseable model output")
            return self.truths[schema]
        return RunnableLambda(respond)


def _docs(tmp_path, applicant_id):
    return make_applicant_documents(tmp_path / applicant_id, applicant_name=NAMES[applicant_id],
                                    **DOCUMENT_SPECS[applicant_id])


def _verify(docs, name, **llm_kwargs):
    return verify_income(name, {k: d.pdf_path for k, d in docs.items()}, llm=_TruthLLM(docs, **llm_kwargs))


@pytest.mark.parametrize("applicant_id", sorted(DOCUMENT_SPECS))
def test_seeded_documents_verify_as_intended(tmp_path, applicant_id):
    result = _verify(_docs(tmp_path, applicant_id), NAMES[applicant_id])
    documented = DOCUMENT_SPECS[applicant_id]["documented_annual_income"]
    # Gross pay is rounded to cents per period, so annualizing drifts by < $1.
    assert result["verified_annual_income"] == pytest.approx(documented, abs=1)
    if applicant_id == "APP-1006":  # tampered pay stub
        assert not result["verification_passed"]
        assert any("gross" in i for i in result["issues"])
        assert any("no bank deposit matches" in i for i in result["issues"])
    else:
        assert result["verification_passed"], result["issues"]


def test_inflated_income_case_documents_less_than_stated(tmp_path):
    stated = next(a for a in SYNTHETIC_APPLICANTS if a["applicant_id"] == "APP-1005")["annual_income"]
    result = _verify(_docs(tmp_path, "APP-1005"), NAMES["APP-1005"])
    assert result["verification_passed"]  # the documents are genuine...
    assert result["verified_annual_income"] < stated * 0.9  # ...they just don't support the stated income


def test_name_mismatch_fails_verification(tmp_path):
    result = _verify(_docs(tmp_path, "APP-1001"), "Someone Else")
    assert not result["verification_passed"]
    assert sum("does not match applicant" in i for i in result["issues"]) == 2


def test_extraction_failure_fails_verification(tmp_path):
    result = _verify(_docs(tmp_path, "APP-1001"), NAMES["APP-1001"], fail=True)
    assert not result["verification_passed"]
    assert result["verified_annual_income"] is None


def test_missing_documents_fail_verification():
    result = verify_income("Anyone", {}, llm=_TruthLLM({}))
    assert not result["verification_passed"]
    assert result["issues"] == ["no pay_stub on file", "no bank_statement on file"]


def test_mirrored_pairs_get_identical_documents_except_name(tmp_path):
    # Fair lending eval validity: if Group A and Group B documents differed in
    # anything but the name, an approval gap could come from the documents
    # rather than the agent.
    ids = {a["applicant_id"] for a in MIRRORED_APPLICANTS}
    pairs = [(a, "APP-3" + a[5:]) for a in sorted(ids) if a.startswith("APP-2")]
    assert pairs and all(b in ids for _, b in pairs)
    for a, b in pairs:
        docs_a, docs_b = _docs(tmp_path, a), _docs(tmp_path, b)
        for doc_type in docs_a:
            ta, tb = docs_a[doc_type].truth, docs_b[doc_type].truth
            assert docs_a[doc_type].layout == docs_b[doc_type].layout
            name_field = "employee_name" if doc_type == "pay_stub" else "account_holder"
            assert ta.model_copy(update={name_field: ""}) == tb.model_copy(update={name_field: ""}), (a, b, doc_type)
