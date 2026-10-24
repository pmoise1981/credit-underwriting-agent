# PDF -> typed document. Text comes from pdfplumber (layout mode, so column
# position survives — on a statement with separate WITHDRAWALS / DEPOSITS
# columns, the column is the only thing that carries the sign). The LLM then
# fills the Pydantic schema via structured output, so the result is a parsed
# model or an exception — never free text that needs a second parsing pass.
from pathlib import Path

import pdfplumber
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from extraction.schemas import SCHEMAS, DocType

EXTRACTION_INSTRUCTION = (
    "You extract data from financial documents into the given schema. "
    "Report values exactly as the document states them. Do NOT correct, recompute, or reconcile anything: "
    "if the stated totals do not add up, extract the stated totals anyway — a separate validation step checks consistency. "
    "Use current-period figures, never year-to-date figures, unless the field name says year-to-date. "
    "Write dates as YYYY-MM-DD. Amounts are plain numbers without currency symbols or thousands separators. "
    "Amounts shown in parentheses or with a trailing minus are negative. "
    "For bank transactions, deposits/credits are positive and withdrawals/debits are negative, "
    "whichever column or notation the document uses. Do not include opening/closing balance rows as transactions."
)


def pdf_to_text(pdf_path: str | Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text(layout=True) or "" for page in pdf.pages]
    # Layout mode pads every line to page width; trailing spaces are pure token cost.
    return "\n\n".join(
        f"--- page {i} ---\n" + "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
        for i, text in enumerate(pages, start=1)
    )


def extract_document(pdf_path: str | Path, doc_type: DocType, llm=None) -> BaseModel:
    """Extracts one document into its schema. Raises if the model's output
    can't be parsed into the schema."""
    if llm is None:
        from config import llm  # deferred: building the Bedrock client needs AWS config
    structured = llm.with_structured_output(SCHEMAS[doc_type])
    result = structured.invoke([
        SystemMessage(content=EXTRACTION_INSTRUCTION),
        HumanMessage(content=f"Document type: {doc_type}\n\n{pdf_to_text(pdf_path)}"),
    ])
    if not isinstance(result, SCHEMAS[doc_type]):
        raise ValueError(f"structured output did not return a {SCHEMAS[doc_type].__name__}: {result!r}")
    return result


if __name__ == "__main__":
    import argparse

    from extraction.validators import validate_document

    parser = argparse.ArgumentParser(description="Extract and validate one financial document.")
    parser.add_argument("pdf")
    parser.add_argument("--type", required=True, choices=list(SCHEMAS))
    args = parser.parse_args()
    doc = extract_document(args.pdf, args.type)
    print(doc.model_dump_json(indent=2))
    violations = validate_document(doc)
    print("VALID" if not violations else "NEEDS HUMAN REVIEW:\n  " + "\n  ".join(violations))
