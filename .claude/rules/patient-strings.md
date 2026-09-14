---
paths:
  - "backend/app/delivery/**"
  - "backend/app/channels/**"
  - "backend/app/consent/**"
  - "ios/Nura/**"
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
