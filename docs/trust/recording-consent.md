# Recording consent: the pattern, and the questions for counsel

**Story** E16-02 · **Acceptance** doctor notified aloud or by printed notice; consent stored · **Status** pattern built; legal review in Singapore and Malaysia open

Nura records a visit so that what the doctor said becomes a summary in the patient's language the same day and a memo in his words (E05). A recording is the most sensitive thing the record holds, and it captures a second person — the doctor — who is not Nura's user. This document is the pattern the app follows every time, where each piece lives in the code, and the questions counsel has to answer in each country before the first family records a visit. It states the questions, not the conclusions: the conclusions are counsel's.

The consent wording itself already exists: `ConsentPurpose.RECORDING`, version 1, in English, Malay and Chinese, in `backend/app/consent/texts.py`. What this story adds is the pattern around it: `backend/app/safety/recording.py` and this document.

---

## 1. The pattern, in order

| Step | What happens | Where it lives |
|---|---|---|
| 1. Consent in force | The patient (or his chief, on a recorded basis) has agreed to the RECORDING words, and has not withdrawn. The surface asks the gate before the microphone opens; there is no path around it. | `may_record` → `require_consent(RECORDING, scope=VISITS)`; refusals on the trail |
| 2. The doctor is named | The visit on the spine names its provider, so the notice can say "Dr Tan"; without one it says "your doctor". | `Appointment.provider_id`; `YOUR_DOCTOR` in `boundary.py` |
| 3. The notice | Before recording starts the app speaks the notice aloud in the patient's language, ending with a question to the doctor by name. The patient also carries a printed card with the same words, for a doctor who would rather read it, or a clinic that wants it on the desk. | `recording_notice`, `printed_notice` |
| 4. The answer is kept | The doctor's answer — a spoken yes — is the first seconds of the recording. Where the printed notice was used instead, the surface records `captured_via = PAPER`. Nothing is trimmed from the start of an artefact, ever. | the VOICE artefact; `ConsentChannel` |
| 5. Stop is one tap | The patient or the key holder in the room can stop at any moment; a stopped recording is kept as far as it went, with its start. | the recording surface (E02-05) |
| 6. On a no | If the doctor or the patient says no, nothing is recorded, and the patient is told who writes the notes by hand: "Nura does not keep this visit. Ash will write the notes by hand." | `when_no` |

The steps are named in the code so that this document and the code can be checked against each other: `recording_consent_in_force`, `doctor_named_or_your_doctor`, `notice_spoken_or_printed`, `answer_kept_as_first_seconds`, `stop_is_one_tap`, `no_means_nothing_kept` (`CHECKLIST` in `recording.py`; `tests/test_recording.py` holds them to this page).

## 2. The words

Every line passes `docs/plain-words.md` (`make plain-words`; `tests/test_recording.py`). `{doctor}` is the provider's name from the spine, or "your doctor".

**Spoken in the room, before recording starts**

| | |
|---|---|
| English | Nura is about to listen and keep what is said. / Only you and the family you choose can hear it. / Is that OK, Dr Tan? |
| Malay | Nura akan mendengar dan menyimpan apa yang dikatakan. / Hanya anda dan keluarga yang anda pilih boleh mendengarnya. / Boleh, Dr Tan? |
| Chinese | Nura 现在要听，并保存说过的话。/ 只有您和您选的家人可以听。/ Dr Tan，可以吗？ |

**Printed card for the clinic desk**

| | |
|---|---|
| English | This patient uses Nura. / Nura listens to this visit and keeps what is said. / Only the patient and the family they choose can hear it. / Please say if you would rather it did not. |
| Malay | Pesakit ini menggunakan Nura. / Nura mendengar lawatan ini dan menyimpan apa yang dikatakan. / Hanya pesakit dan keluarga yang dipilihnya boleh mendengarnya. / Sila beritahu jika anda tidak mahu. |
| Chinese | 这位病人使用 Nura。/ Nura 会听这次看诊，并保存说过的话。/ 只有病人和他选的家人可以听。/ 如果您不希望这样，请告诉我们。 |

**When the answer is no**

| | |
|---|---|
| English | Nura does not keep this visit. / Ash will write the notes by hand. |
| Malay | Nura tidak menyimpan lawatan ini. / Ash akan menulis nota dengan tangan. |
| Chinese | Nura 不保存这次看诊。/ Ash 会用手写下笔记。 |

The Malay and Chinese lines are a first translation awaiting a native speaker's pass, like the consent texts.

## 3. Where it is stored

- **The agreement**: one `consent` row, purpose `recording`, with the words as read, the language, `captured_via` (app, WhatsApp, paper, or a witnessed spoken yes), the basis (`owner`, or a proxy basis with the document or the recording behind it), when it was given and when withdrawn. The row outlives the graph (`ondelete="RESTRICT"`; see `pdpa-data-map.md` §4).
- **The recording**: one `artifact` row of kind `voice`, the bytes in the object store of the profile's region under `storage_key`, the digest on the row, and nothing of the content anywhere in the database. The transcript, the summary and the memo (E05) are facts and artefacts that name this artefact as their provenance.
- **The doctor's answer**: the first seconds of that artefact. It is not a separate row and it is not transcribed into a column; if it is ever needed it is played.
- **Who has heard it**: every read of the artefact is an `audit_entry` the owner can see.

What is not stored: the doctor's name against the recording as a person Nura knows. The doctor is a `provider` row on the patient's own profile — a directory entry the patient keeps, not an account — and providers are never linked across profiles.

## 4. What the app enforces, and what it does not

Enforced by code, with a test each: the gate (`may_record`), the notice in the patient's language, the scope of the gate (a key without `visits` cannot start a recording and cannot learn from the gate whether the patient agreed), the refusal on the trail. Owed by the recording surface when it lands (E02-05, E05), and held to this page by its own tests: speaking the notice before the microphone opens, keeping the answer as the first seconds, one-tap stop, and the no path.

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

## 6. Malaysia — positions to be reviewed by counsel

Same working assumption; the profile and the bytes are in Malaysia. Questions:

1. **Scope of the Personal Data Protection Act 2010.** The Act applies to personal data processed in respect of commercial transactions. Is a family's recording of a consultation, held by a paid app, within it as to the doctor's personal data? Section 45's exemptions for personal, family or household affairs — do they reach the patient, and do they reach Nura?
2. **Sensitive personal data.** Health information is sensitive personal data (s 40) and needs explicit consent. The patient gives it; the doctor's words about the patient are the patient's health data — is any part of the recording the doctor's own sensitive personal data?
3. **Interception.** Is a participant recording his own consultation an "interception" under s 234 of the Communications and Multimedia Act 1998, or outside it? This decides whether a doctor's refusal must be honoured as a matter of law rather than courtesy.
4. **Private healthcare facilities.** Does the Private Healthcare Facilities and Services Act 1998 or its regulations let a facility prohibit recording, and how should the printed card acknowledge that?
5. **Professional guidance.** The Malaysian Medical Council's Code of Professional Conduct — anything on consultations being recorded by patients?
6. **The 2024 amendments.** The Personal Data Protection (Amendment) Act 2024 adds data-processor duties, breach notification and a data protection officer. Which of these attach to Nura as the holder of the recording, and from when?
7. **Cross-border visits.** A Malaysian profile recorded in a Singapore clinic, or the reverse: the bytes stay in the profile's region; is the doctor's personal data then transferred across the border, and under which country's rule?

## 7. Open product decisions that wait on counsel

- Whether the app should refuse to record when the visit has no named provider, rather than saying "your doctor".
- Whether the spoken notice should repeat in the doctor's language when it differs from the patient's.
- Whether the printed card carries a QR code to this page.
- Whether a doctor's "no" is stored as an event on the visit (so the memo says why there is no summary) — today the app simply does not record.
- How long a recording is kept once its summary and memo exist and have been read (see `pdpa-data-map.md` §4).

## 8. Sign-off

| Country | Counsel | Date | Outcome |
|---|---|---|---|
| Singapore | | | |
| Malaysia | | | |

No visit is recorded on a real profile until both rows are filled.
