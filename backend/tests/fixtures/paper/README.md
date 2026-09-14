# Paper fixtures

The first family's redacted papers, as the extraction sessions read them: the lab report and the medicine label (E02-01), a clinic slip and a prescription written by hand (E02-02), a hospital letter and a receipt as PDFs (E02-03), the screens of a blood pressure machine and a glucometer (E02-08), and a second lipid panel from a fictional lab whose header names the lab, the year of birth and the sex (E09-01, synthetic).

No photo, scan or PDF is committed. Each paper is a JSON file here plus a small deterministic byte string that stands in for it — a PNG signature (or, for a PDF, a `%PDF-1.4` header) and a label, made by `tests/paper.py` (`placeholder_png`, `placeholder_pdf`) and, for the checkpoints, by the same lines in `backend/scripts/checkpoint.py` and `backend/scripts/checkpoints/cp18.py`. The file's `sha256` is the digest of those bytes, and it is how `app.ingestion.extract.FixtureExtractor` knows which paper it is being shown; a digest no file names is a page it cannot read. `format` says which placeholder (`png` unless `pdf`); a PDF also says how many `pages` it has.

Each file says what the extractor reads off the paper: `document_kind`, `document_date`, and `fields` — subject, attribute, value, unit, confidence and where on the page (`span`, fractions of the image, with `page` for a PDF of several pages). A field the recogniser saw and could not read is `"unreadable": true` with `"value": null`: never a guess, and the card asks a person to type it. A `note` says what was redacted and anything deliberate about the reading (a misread left in at low confidence so a review card has something to correct); keys the extractor does not know, such as `paper_says`, are documentation and never reach a card.

## The labelled test set (docs/build-plan.md §8, risk 1)

Beside every paper is `<label>.expected.json`: what the paper actually says, labelled by hand. It is the answer the extractor is measured against, and it does not name a digest, so the extractor never reads it. `tests/paper_accuracy.py` runs every pair through the pipeline — the bytes, the extractor with its hint, the checks every field passes before it reaches a card — and prints, field by field, whether the value was read right, put in front of a person (dotted below the confidence threshold, or unreadable), or silently wrong. Run it with

```sh
cd backend && python3 -m tests.paper_accuracy
```

`tests/test_paper_accuracy.py` runs the same harness in `make test` and asserts that on these fixtures every field is either read right or put in front of a person: nothing silently wrong, nothing dropped, nothing invented. It prints the read accuracy beside it; the fixtures misread two fields on purpose (the lipid panel's triglycerides, the clinic slip's frequency), so that number is below 100% and is the one to watch when the real extractor lands.

## Adding one of your own papers

1. **Redact it first.** Cover names, IC and passport numbers, addresses, phone numbers, hospital and registration numbers, barcodes and QR codes before the file leaves your phone. Keep a copy of the original somewhere that is not this repository.
2. **Name it** `<what>-<date on the paper>`, for example `kidney-test-2026-10-02`, and put the redacted file here as `<label>.jpg`, `.png`, `.heic` or `.pdf`. The harness reads a real file when there is one and the placeholder only when there is not.
3. **Label it**: write `<label>.expected.json` with what the paper says — copy the shape of `clinic-slip-2026-09-10.expected.json`: `placeholder` (the label), a `note` saying what you redacted, `document_kind`, and `fields` as `subject`, `attribute`, `value` and `unit`, one per thing on the paper you would want on the record. Write the value exactly as it should be kept: numbers as numbers, dates as `YYYY-MM-DD`.
4. **Until the real extractor exists**, also write `<label>.json` — what the fixture extractor reads off it, with the real file's `sha256` (`shasum -a 256 <file>`) — or the harness will report every field as dropped, which is the honest answer for a page nothing can read.
5. Run `python3 -m tests.paper_accuracy` and `make test`. Every week, the harness line is the number to write down.

Formats: jpg, png, heic, pdf.
