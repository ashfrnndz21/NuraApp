# ADR 0006 — Consult recording on the web: what the browser can do, the order, what is kept

**Date** 2026-09-15 · **Status** proposed · **Decided by** the operator, for the owner · **Stories** E05-04, E02-05, E03-05 (the clip), E05-03 (the logistics the Visit screen opens on)

## Context

ADR 0001 made the first client a web app. E05-04 and E02-05 ask for a visit to be recorded with one tap, the consent prompt first, the transcript searchable, who spoke when, and a clip playable at a timestamp. `docs/trust/recording-consent.md` sets the pattern and the checklist the surface owes; ADR 0003 says a recording of a visit is a consult (`Recording.CONSULT`) and rests on the RECORDING consent. A browser is not a native app: it records only while its page is in front, it may be put to sleep, it records in whatever container its engine has, and it cannot cut audio without a demuxer. This ADR records how the web surface keeps the pattern within those limits.

## Decision

### The order, and where each checklist step lives

| Step (`CHECKLIST`) | On the web | Held by |
|---|---|---|
| `recording_consent_in_force` | Tapping **Start recording** first asks the server for the notice (`GET …/appointments/{appt}/recording/notice`). The server refuses a key that does not change the visits, then asks the gate (`may_record`). Without the consent in force it answers `ConsentWithheld` and the owner is shown today's RECORDING words (`GET /consent/wording?purpose=recording`) and one **I agree** (`POST …/consents/recording`); anyone else is told the owner has not agreed. The microphone is not asked for until the gate has passed. On the upload the gate is asked again, and `store_artifact` asks the consent a third time where the bytes land. | `app/ingestion/consult.py: notice_for, record_consult`; `app/memory/episodic.py`; `tests/test_visit_day.py`; `web/tests/e2e/visit.spec.ts` |
| `records_scope_held` | The same gate: a viewer's key, which holds visits and not records, is refused before the room is told anything. | `may_record`; `tests/test_visit_day.py` |
| `doctor_named_or_addressed_plainly` | The notice comes from the server, from the visit's provider (`recording_notice`), never from a string on the phone. The row keeps `doctor_named`. | `consult_recording.doctor_named` |
| `notice_spoken_or_printed` | The notice is shown and spoken through the one speech seam (`speak()`, a voice on the phone only) the moment it arrives, in the same tap. The printed card is in the same answer for a doctor who would rather read it. | `web/src/screens/Visit.tsx` |
| `answer_kept_as_first_seconds` | The recorder starts as soon as the notice has been spoken, so the recording opens with the notice itself and then the doctor's answer. Nothing is trimmed from its start, on the phone or on the server. The screen asks "Did Dr Tan say yes?" while the red dot is already on. | `web/src/visit/recorder.ts`; the VOICE artefact |
| `stop_is_one_tap` | **Stop** is one big button on the recording screen. The page's own **Stop** is the only thing that uploads. | `web/src/screens/Visit.tsx` |
| `no_means_nothing_kept` | **Dr Tan said no** stops the recorder and throws the audio away on the phone. Nothing was uploaded, so nothing is kept. The screen shows the server's words for a no (`when_no`) and offers the notes by hand: E05's typed transcript, read into the same card. | `web/src/visit/recorder.ts: discard`; `tests/test_visit_day.py: test_a_no_keeps_nothing`; the e2e "no" test |

### What the browser cannot do, said on the screen

- **The page must stay in front.** A phone browser suspends a page it hides. When the page is hidden while recording (`visibilitychange`), the recorder is stopped at once and what it heard is kept on the phone. The screen then says "Nura stopped listening when you left this page." with one button, **Keep what Nura heard**, which uploads it. A recording that was still waiting for the doctor's answer is thrown away, as on a no. Before and during recording the screen says: "Keep this page open while Nura listens."
- **The screen stays on.** A screen wake lock is asked for while recording (`navigator.wakeLock`), and released on Stop, on a no, and when the page is hidden. Where the browser has no wake lock, nothing else changes: the line above still holds.
- **The container is the browser's.** Chrome and Android record opus in webm, which is preferred. Firefox records opus in ogg. Safari on the iPhone records AAC in mp4, as `MediaRecorder` does there. The server accepts exactly these three (`CONSULT_CONTENT_TYPES`) and checks that the first bytes are that container's, a size (48 MB) and a length (90 minutes) a visit has.
- **Nothing uploads until Stop.** The audio is held in the page's memory as the recorder hands it over, and is sent once, as the request body of `POST …/appointments/{appt}/recording`. If the upload fails the screen says so and keeps the audio, so **Stop** can send it again. Nothing is written to the phone's storage.

### The clip: the whole artefact, with the stretch to play

A citation of a consult carries `start_s` and `end_s`, from the speaker segments the item's words fall in. A byte range of a webm or an mp4 is not a playable file: the header and the cues are at the front, and the clusters do not line up with seconds. Cutting a real clip needs a demuxer, which is a new dependency. So `GET /profiles/{id}/artifacts/{a}/clip?start=&end=` answers with the whole artefact under the artefact's own scope — the visits scope to find the recording, the record's to read its bytes — with the stretch in `X-Clip-Start`, `X-Clip-End` and `X-Media-Fragment: t=start,end`. The phone plays it as a media fragment, sets the start itself when the fragment is ignored, and pauses at the end. This is the honest choice: anyone who can hear the clip can already hear the whole recording (the same scopes), so nothing is disclosed that the scopes did not already open. What is disclosed is exactly what the trail says was read.

### What is stored

- The recording: one `artifact` of kind `voice`, declared `Recording.CONSULT`, its bytes under `consults/<profile>/<sha256>` in the region's object store.
- The words heard: one `artifact` of kind `transcript`, bytes in the same store; never a column.
- `consult_recording`: which visit, which artefacts, the RECORDING consent it rested on (`consent_id`), how long the phone listened, the notice's language, whether the doctor was named, how sure the transcriber was, who pressed Start.
- `consult_segment`: who spoke (patient, doctor, family, unknown), from when to when in seconds, and where those words are in the transcript by character offset. Never the words.
- `visit_summary.recording_artifact_id` and `summary_item.clip_start_s`/`clip_end_s`: where on the recording each line of the card was said.

The speech and speaker providers are ports with fixtures (`Transcriber`, `SpeakerSeparator`): no audio leaves the region, and no live provider is called. A deployment with no separator keeps a recording as one stretch by an unknown speaker (`Unseparated`), which claims nothing it did not hear.

## Consequences

- The web surface holds the pattern within the browser's limits. The limits are said on the screen, not hidden.
- `docs/trust/recording-consent.md` §4's "owed by the recording surface" items are now held by tests: `tests/test_visit_day.py` for the server's half, and `web/tests/e2e/visit.spec.ts` (with a stand-in `MediaRecorder`) for the notice spoken before the microphone opens, the answer kept as the first seconds, one-tap stop, and the no path.
- A native client later records in the background. This ADR's hidden-page rule is the web's, not the product's.
- Counsel's sign-off (recording-consent.md §8) still gates recording on a real profile; nothing here changes that.
- Open: whether the recording should upload in chunks for a long visit on a weak network (today: once, on Stop); how long a recording is kept once its card is read (pdpa-data-map §4, question 4 for counsel).
