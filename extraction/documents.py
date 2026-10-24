# Document store stand-in: returns the PDFs on file for an applicant. Here they
# are rendered on demand from data_seed.DOCUMENT_SPECS into the temp dir
# (deterministic, and writable on Lambda); in production this would fetch the
# applicant's uploaded documents from S3. Callers only see doc_type -> path,
# so swapping the backing store doesn't touch extraction or verification.
import tempfile
from pathlib import Path

from data_seed import DOCUMENT_SPECS, SYNTHETIC_APPLICANTS
from extraction.synth import make_applicant_documents

_NAMES = {a["applicant_id"]: a["name"] for a in SYNTHETIC_APPLICANTS}


def get_applicant_documents(applicant_id: str) -> dict[str, Path]:
    """doc_type -> PDF path. Empty if the applicant has no documents on file."""
    spec = DOCUMENT_SPECS.get(applicant_id)
    if spec is None:
        return {}
    out_dir = Path(tempfile.gettempdir()) / "underwriting-docs" / applicant_id
    docs = make_applicant_documents(out_dir, applicant_name=_NAMES[applicant_id], **spec)
    return {doc_type: doc.pdf_path for doc_type, doc in docs.items()}
