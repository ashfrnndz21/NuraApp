# Recording consent: the pattern, and the questions for counsel

**Story** E16-02 · **Acceptance** doctor notified aloud or by printed notice; consent stored · **Status** pattern built; legal review in Singapore and Malaysia open

Nura records a visit so that what the doctor said becomes a summary in the patient's language the same day and a memo in his words (E05). A recording is the most sensitive thing the record holds, and it captures a second person — the doctor — who is not Nura's user. This document is the pattern the app follows every time, where each piece lives in the code, and the questions counsel has to answer in each country before the first family records a visit. It states the questions, not the conclusions: the conclusions are counsel's.

The consent wording itself already exists: `ConsentPurpose.RECORDING`, version 1, in English, Malay and Chinese, in `backend/app/consent/texts.py`. What this story adds is the pattern around it: `backend/app/safety/recording.py` and this document.

---

## 1. The pattern, in order

| Step | What happens | Where it lives |
|---|---|---|
| 1. Consent in force | The patient (or his chief, on a recorded basis) has agreed to the RECORDING words, and has not withdrawn. The surface asks the gate before the microphone opens; and where the bytes enter, `store_artifact` asks the same consent for every consult recording (`Recording.CONSULT`), so no writer — the app, WhatsApp, a connector — can keep a recording of a visit without it. | `may_record` → `require_consent(RECORDING, scope=VISITS)`; `app/memory/episodic.py: store_artifact(recording=…)`; refusals on the trail |
| 1a. The key can keep it | The person recording holds the records scope, the door every artefact is kept through (`store_artifact`); the recording itself is then written under the visits scope, where it is heard (ADR 0004). A viewer key holds visits and not records: the gate refuses her before the room is told anything, so nobody hears "Nura will listen now" and then finds nothing was kept. | `may_record` → `context.require(RECORDS)`; the refusal on the trail as a refused write of an artefact |
| 2. The doctor is named | The visit on the spine names its provider, so the notice can say "Dr Tan". Without one the other lines say "your doctor" and the last line — the one addressed to the doctor — says "doctor" plainly: "Is that OK, doctor?", never "your doctor", which is not a form of address. | `Appointment.provider_id`; `YOUR_DOCTOR` in `boundary.py`; `VOCATIVE_LINE` |
| 3. The notice | Before recording starts the app speaks the notice aloud in the patient's language, ending with a question to the doctor by name. The patient also carries a printed card with the same words, for a doctor who would rather read it, or a clinic that wants it on the desk. | `recording_notice`, `printed_notice` |
| 4. The answer is kept | The doctor's answer — a spoken yes — is the first seconds of the recording. Where the printed notice was used instead, the surface records `captured_via = PAPER`. Nothing is trimmed from the start of an artefact, ever. | the VOICE artefact; `ConsentChannel` |
| 5. Stop is one tap | The patient or the key holder in the room can stop at any moment; a stopped recording is kept as far as it went, with its start. | the recording surface (E02-05) |
| 6. On a no | If the doctor or the patient says no, nothing is recorded, and the patient is told who writes the notes by hand: "Nura will not listen today. Ash will write the notes by hand." (Not "keep this visit": to keep a visit is to attend it.) | `when_no` |

**What this consent covers, and what it does not** (ADR 0003, `docs/adr/0003-recording-consent-covers-other-voices.md`). The RECORDING consent gates recordings that capture people other than the account holder — a visit with the doctor, E05's consult transcripts, E02-05's recording surface. A person's own voice note about himself — a note on an event, a not-feeling-well message, a symptom said aloud — is his own words, kept on the consent to hold the record like typed text; a caregiver's voice note on his event is hers, kept on his consent to hold the record and her key's scope. Every writer of a voice declares which it is (`Recording.CONSULT` or `Recording.OWN_NOTE`) where the bytes enter, and cannot leave it out.

The steps are named in the code so that this document and the code can be checked against each other: `recording_consent_in_force`, `records_scope_held`, `doctor_named_or_addressed_plainly`, `notice_spoken_or_printed`, `answer_kept_as_first_seconds`, `stop_is_one_tap`, `no_means_nothing_kept` (`CHECKLIST` in `recording.py`; `tests/test_recording.py` holds them to this page).

## 2. The words

Every line passes `docs/plain-words.md` (`make plain-words`; `tests/test_recording.py`). `{doctor}` is the provider's name from the spine, or "your doctor".

**Spoken in the room, before recording starts**

| | |
|---|---|
| English | Nura will listen now. / Nura keeps what you and Dr Tan say. / Only you and the family you let in can hear it. / Is that OK, Dr Tan? |
| Malay | Nura akan mendengar sekarang. / Nura menyimpan apa yang anda dan Dr Tan kata. / Hanya anda dan keluarga yang anda benarkan boleh mendengarnya. / Boleh, Dr Tan? |
| Chinese | Nura 现在开始听。/ Nura 会保存您和Dr Tan说的话。/ 只有您和您让进来的家人可以听。/ Dr Tan，可以吗？ |

With no doctor named, the last line is: Is that OK, doctor? / Boleh ya, doktor? / 医生，可以吗？

"The family you let in" is the consent's own phrase (`texts.py`), word for word. Until E05-04 the notice said "those you let in", widened by one word because a clinic key holding the visits could hear a recording. Access is now narrowed instead, to match the printed card ("Only the patient can hear it. The patient can let his family hear it too.") and the words he agreed to: a visit's recording, its clips and the transcript heard from it are heard only by the patient and the family he let in — his chief and his caregivers. The artefact door refuses every other key even when it holds the visits — a viewer, a clinic, a helper, an emergency key — in plain words and on his trail (`OnlyTheFamilyHears`, `app/memory/episodic.py`). A clinic key reads the visit and its card, not what was said in the room.

**Printed card for the clinic desk**

| | |
|---|---|
| English | This patient uses Nura. / Nura listens to what you and the patient say. / Nura keeps it for the patient to hear again. / Only the patient can hear it. / The patient can let his family hear it too. / You can say no. / Then Nura does not listen. |
| Malay | Pesakit ini menggunakan Nura. / Nura mendengar apa yang anda dan pesakit kata. / Nura menyimpannya untuk pesakit dengar semula. / Hanya pesakit boleh mendengarnya. / Pesakit boleh benarkan keluarganya mendengar juga. / Anda boleh kata tidak. / Nura tidak akan mendengar. |
| Chinese | 这位病人使用 Nura。/ Nura 会听您和病人说的话。/ Nura 会保存下来，让病人再听。/ 只有病人可以听。/ 病人也可以让家人听。/ 您可以说不。/ Nura 就不会听。 |

**When the answer is no**

| | |
|---|---|
| English | Nura will not listen today. / Ash will write the notes by hand. |
| Malay | Nura tidak akan mendengar hari ini. / Ash akan menulis nota dengan tangan. |
| Chinese | Nura 今天不会听。/ Ash 会用手写下笔记。 |

The Malay and Chinese lines are a first translation awaiting a native speaker's pass, like the consent texts.

## 3. Where it is stored

- **The agreement**: one `consent` row, purpose `recording`, with the words as read, the language, `captured_via` (app, WhatsApp, paper, or a witnessed spoken yes), the basis (`owner`, or a proxy basis with the document or the recording behind it), when it was given and when withdrawn. The row outlives the graph (`ondelete="RESTRICT"`; see `pdpa-data-map.md` §4).
- **The recording**: one `artifact` row of kind `voice`, the bytes in the object store of the profile's region under `storage_key`, the digest on the row, and nothing of the content anywhere in the database. The transcript, the summary and the memo (E05) are facts and artefacts that name this artefact as their provenance.
- **On its way in** (#129, ADR 0013): while the visit is recorded, the phone sends the audio in chunks, from the notice on, so the doctor's answer is in the first of them. The chunks wait in the region's object store under `consult-uploads/<profile>/<upload>/`; no route reads them back, and they are not an artefact, a transcript or a card. They are kept as the recording only after the doctor's yes. They are deleted on his no, when the page is left before he answers, when nobody answers within fifteen minutes (up to about twenty when the phone could not say so, until the scheduler's next five-minute run), when the visit is not finished within two and a half hours, when the RECORDING consent is withdrawn, and when the account is closed. Before #129 nothing left the phone until Stop (ADR 0006).
- **The doctor's answer**: the first seconds of that artefact. It is not a separate row and it is not transcribed into a column; if it is ever needed it is played.
- **Who has heard it**: every read of the artefact is an `audit_entry` the owner can see. Who *can* hear it is the patient and the family he let in — a chief or a caregiver key — and nobody else: the recording and its transcript are written under the visits scope (row scope, ADR 0004), and the artefact door refuses a consult to any other key even when it holds the visits (a viewer, a clinic, a helper, an emergency key; `OnlyTheFamilyHears`, on his trail). Access was narrowed to this in E05-04 so that it matches the printed card and the words he agreed to. A stretch of it is played through the same door: `GET /profiles/{id}/artifacts/{a}/clip` (ADR 0006). The notice says "the family you let in" for that reason. A person's own voice note keeps its own rule (ADR 0003).
- **Who else handles it**: the bytes go to a speech provider for transcription and to the model for the sentence of the summary (E05), on region-pinned endpoints, under contract not to keep or train on them (`pdpa-data-map.md` §5). The notice does not name them, because they hold nothing once the transcript is back; whether it must is question 8 for counsel in each country.

What is not stored: the doctor's name against the recording as a person Nura knows. The doctor is a `provider` row on the patient's own profile — a directory entry the patient keeps, not an account — and providers are never linked across profiles.

## 4. What the app enforces, and what it does not

Enforced by code, with a test each: the gate (`may_record`: the consent under `visits`, the reach under `records`), the same consent again where the bytes enter (`store_artifact` for every VOICE artefact, whoever writes it), the notice in the patient's language with the doctor addressed plainly when unnamed, the scope of the gate (a key without `visits` cannot start a recording and cannot learn from the gate whether the patient agreed; a key without `records` is refused before the room is told anything), every refusal on the trail. Owed by the recording surface when it lands (E02-05, E05), and held to this page by its own tests: speaking the notice before the microphone opens, keeping the answer as the first seconds, one-tap stop, and the no path.

Not enforced by code, and cannot be: whether the doctor actually heard the notice, and whether the clinic's own rules allow recording on its premises. The printed card exists for the second; the first is why the answer is kept.

## 5. Singapore — positions to be reviewed by counsel

Nura's working assumption, stated so counsel can correct it: the recording is made by the patient, of his own consultation, with the doctor told beforehand and his answer kept; Nura holds it for the patient, in Singapore, under the patient's explicit consent. Questions:

1. **Personal data of the doctor.** The recording contains the doctor's voice and words. Under the Personal Data Protection Act 2012, is Nura collecting the doctor's personal data, and if so on what basis — the doctor's consent as spoken, deemed consent by notification (Part IV, as amended in 2020), or a "personal or domestic" purpose of the patient's that Nura processes as a data intermediary? Does the answer change when the chief, not the patient, is the one recording?
2. **One-party recording.** Is there any statutory bar on a participant recording his own consultation without the doctor's agreement? The pattern asks anyway; counsel should confirm whether the ask is courtesy or requirement, because that decides what a doctor's silence means.
3. **The clinic's rules.** Does the Healthcare Services Act 2020 or any licence condition under it give a licensee the right to prohibit recording on its premises, and what should the printed card say about that?
4. **Professional guidance.** Does the Singapore Medical Council's Ethical Code and Ethical Guidelines say anything about a patient recording a consultation that the notice should acknowledge?
5. **The doctor's rights over the recording.** Can the doctor later ask for a copy, or for erasure of his voice, and how should the app answer?
6. **Third parties in the room.** A nurse, an interpreter, another patient. Does the notice cover them, or must recording stop?
7. **Deemed consent versus explicit.** If the doctor keeps talking after the notice, is that consent? The pattern keeps the answer for exactly this question.
8. **The processors.** The recording goes to a speech provider and a model provider for the transcript and the summary. Must the notice name them, and what must the contract with each say about retention and training?

## 6. Malaysia — positions to be reviewed by counsel

Same working assumption; the profile and the bytes are in Malaysia. Questions:

1. **Scope of the Personal Data Protection Act 2010.** The Act applies to personal data processed in respect of commercial transactions. Is a family's recording of a consultation, held by a paid app, within it as to the doctor's personal data? Section 45's exemptions for personal, family or household affairs — do they reach the patient, and do they reach Nura?
2. **Sensitive personal data.** Health information is sensitive personal data (s 40) and needs explicit consent. The patient gives it; the doctor's words about the patient are the patient's health data — is any part of the recording the doctor's own sensitive personal data?
3. **Interception.** Is a participant recording his own consultation an "interception" under s 234 of the Communications and Multimedia Act 1998, or outside it? This decides whether a doctor's refusal must be honoured as a matter of law rather than courtesy.
4. **Private healthcare facilities.** Does the Private Healthcare Facilities and Services Act 1998 or its regulations let a facility prohibit recording, and how should the printed card acknowledge that?
5. **Professional guidance.** The Malaysian Medical Council's Code of Professional Conduct — anything on consultations being recorded by patients?
6. **The 2024 amendments.** The Personal Data Protection (Amendment) Act 2024 adds data-processor duties, breach notification and a data protection officer. Which of these attach to Nura as the holder of the recording, and from when?
7. **Cross-border visits.** A Malaysian profile recorded in a Singapore clinic, or the reverse: the bytes stay in the profile's region; is the doctor's personal data then transferred across the border, and under which country's rule?
8. **The processors.** As for Singapore: must the notice name the speech and model providers, and what do the 2024 amendments' processor duties require of those contracts?

## 7. Open product decisions that wait on counsel

- Whether the app should refuse to record when the visit has no named provider, rather than saying "your doctor".
- Whether the spoken notice should repeat in the doctor's language when it differs from the patient's.
- Whether the printed card carries a QR code to this page.
- Whether a doctor's "no" is stored as an event on the visit (so the memo says why there is no summary) — today the app simply does not record.
- How long a recording is kept once its summary and memo exist and have been read (see `pdpa-data-map.md` §4).
- A recording of the patient's *spoken agreement* (the `verbal_recorded` basis, E01) is a VOICE artefact and so itself rests on a RECORDING consent being in force. Today that means the owner has agreed to recording before a chief can keep his spoken yes to anything else. Whether that recording should rest on a narrower footing of its own is for the owner with counsel.

## 8. Sign-off

| Country | Counsel | Date | Outcome |
|---|---|---|---|
| Singapore | | | |
| Malaysia | | | |

No visit is recorded on a real profile until both rows are filled.
