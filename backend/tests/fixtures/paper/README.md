# Paper fixtures

The first family's redacted papers, as the extraction sessions (Session 4, E02-01) read them.

No photo or scan is committed. Each paper is a JSON file here plus a small deterministic byte string that stands in for the photo — a PNG signature and a label, made by `tests/paper.py` (`placeholder_png`) and, for the checkpoint, by the same three lines in `backend/scripts/checkpoint.py`. The file's `sha256` is the digest of those bytes, and it is how `app.ingestion.extract.FixtureExtractor` knows which paper it is being shown; a digest no file names is a page it cannot read.

Each file says what the extractor reads off the paper: `document_kind`, `document_date`, and `fields` — subject, attribute, value, unit, confidence and where on the page (`span`, fractions of the image). A `note` says what was redacted and anything deliberate about the reading (a misread left in at low confidence so a review card has something to correct); keys the extractor does not know, such as `paper_says`, are documentation and never reach a card.

When a real photo is added later: redact names, IC/passport numbers, addresses, phone numbers and barcodes before adding, and write its real sha256 into the file. Formats: jpg, png, heic, pdf.
