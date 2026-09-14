---
paths:
  - "backend/app/audit/**"
  - "backend/app/delivery/**"
  - "backend/app/channels/**"
  - "backend/app/consent/**"
  - "backend/app/family/**"
  - "backend/app/medicines/**"
  - "backend/app/onboarding/**"
  - "backend/app/reasoning/visits/strings.py"
  - "backend/app/safety/boundary.py"
  - "backend/app/safety/recording.py"
  - "ios/Nura/**"
  - "web/src/strings/**"
---
# Patient-facing strings

Every string a patient reads or hears follows `docs/plain-words.md`:
- Whole, natural sentences with a subject. Never fragments ("Only the part for you." is wrong; "We kept only the part that matters for you." is right).
- One idea per line. Under ten words where possible.
- Call things what he calls them: "the water pill", "your blood pressure tablet", "your blood pressure book". Chemical name second and small, never alone.
- Day and date: "Monday 29 September", never "the 29th".
- Say what to do and when; say who does the next thing.
- No red words: no "missed", "failed", "overdue". No abbreviations, no "dose", "recheck", "follow-up", "flag", "log".
- The same words every time.
- Every card is also a voice script: short sentences, pauses, the doctor's name every time.
Run `make plain-words` and fix every failure before committing.

## How to write a patient string

1. Put it in a file under the paths above (`app/channels/strings.py` is the catalogue for a
   sentence the backend writes) and tag the statement it lives in, so the verifier finds it:
   - `# @patient` on the line above an assignment, a `def` or a class tags the whole statement:
     every string literal in it, docstring aside.
   - `# @patient` at the end of a code line tags the statement on that line.
   - `"""@patient ..."""` on the line after an assignment tags that assignment (the idiom in
     `app/channels/strings.py`).
   - The tag may name a kind: `# @patient phrase` for his words for a thing that fill a slot
     ("your papers", "in the app"), `# @patient headline` for a heading, `# @patient action` for
     a card that must say who does the next thing and when. Bare `# @patient` means whole lines.
   - In the iOS strings catalogue (`ios/Nura/**/*.xcstrings`), a comment beginning `patient`
     (optionally with the kind) tags the entry in every language it is localised in.
   - In the web strings (`web/src/strings/{en,ms,zh}.ts`), `// @patient` (optionally with the
     kind) on the line above a property or statement tags every string literal in it, and at
     the end of a line tags that line; the file's name is the language. `npm run plain-words`
     in `web/` checks only those files; `make plain-words` checks them with everything else.
2. Write each line whole, never assembled from pieces at run time: the verifier reads one
   literal at a time, and so does the reviewer. Put `{slots}` in for names, dates and numbers;
   the verifier fills them with "Ash", "Monday 14 September" and "2".
3. Old words that stay as the record but are shown no more (a superseded consent version) carry
   `# plain-words: <reason>` at the end of the line the literal starts on. Nothing that ships
   is exempt.
4. Run `make plain-words`. Each failure is `path:line: rule N — problem → rewrite`, by the rule's
   number in `docs/plain-words.md`; `python3 -m app.safety.plain_words --explain` lists what each
   rule checks and `--text "..."` checks one line. Notes (an eleven-word line) do not fail the
   build; failures do, here and in CI.
5. Text the backend writes at run time (a memo, a card) goes through
   `app.safety.plain_words.verify(text, language, kind)` before it reaches him.
