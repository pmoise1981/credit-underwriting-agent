# Document extraction layer: synthetic financial documents (PDF) -> typed,
# validated data. Sits in front of the underwriting agent so the facts it
# reasons over come from documents, not hand-seeded rows.
#
#   synth.py       synthetic pay stubs / bank statements in several messy layouts,
#                  with ground truth kept alongside each PDF
#   schemas.py     Pydantic models the LLM must fill
#   extractor.py   PDF text (pdfplumber) -> LLM structured output -> schema
#   validators.py  deterministic arithmetic/consistency checks, plain Python
