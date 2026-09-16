# Clinical wording awaiting sign-off

These are the lines on his screen that touch a medicine or a body salt closely enough that a
clinician or the pharmacist must agree the wording before any real profile sees it (CP19, the
first family on real health information). Each row stays open until its adviser, date and
outcome are filled in. Until then the wording ships only on the demo, which holds no real
health information (ADR 0008).

| # | Wording | Where | Who signs | Why it is here | Issue | Status |
|---|---|---|---|---|---|---|
| 1 | Potassium as "your body salt" (en), "garam badan anda" (ms), "您身体的盐" (zh) | `backend/app/delivery/trend_strings.py`, `timeline_strings.py`; glossary row in `docs/plain-words.md` | The pharmacist | Salt substitutes are potassium chloride. So someone told to watch his potassium may reach for "low-salt" salt, and a low result could read as "eat more salt". Keep, pair with the name ("your potassium, a body salt"), or reword. | #126 | Open |
| 2 | The feeling note that names a medicine, and the two lines always said straight after it | `backend/app/reasoning/feelings/strings.py` (`REASON["new_medicine"]`, `DO_NOT_STOP`), put together in `inference.py` | A clinician and the pharmacist | The note tells him his feeling can come from a tablet it names. The two lines after it tell him not to stop the tablet himself and to tell the doctor how he feels. Nothing on the note may read as a diagnosis or a change to a dose. | #157 | Open |

Row 2 in full, as he reads it (`{doctor}` is the doctor the note names, or "your doctor"):

| | en | ms | zh |
|---|---|---|---|
| The medicine line | This can come from {medicine}, new since {date}. | Ini boleh berlaku kerana {medicine}, yang baru sejak {date}. | 这可能和{medicine}有关，它从{date}起是新的。 |
| Straight after it | Do not stop {medicine} yourself. | Jangan berhenti makan {medicine} sendiri. | 不要自己停{medicine}。 |
| Then | Tell {doctor} how you feel. | Beritahu {doctor} apa yang anda rasa. | 告诉{doctor}您的感觉。 |

The note names a medicine only where its licensed monograph lists the feeling as a watch-out
(`WATCH_OUT_WORDS`, `backend/app/reasoning/feelings/words.py`), so these are the feelings the
two lines can follow: dizzy, swollen ankles, muscle ache, cramps and tummy upset. Shaky and
sweaty is a watch-out too, but it is a red word: a tap on it goes to the red-flag path and
never makes a note. The clinician should judge each one; muscle ache on a cholesterol tablet
is the case where "Do not stop" most needs checking. The note also says "Tell {doctor}" twice
(its first line, and the last of these two): keep both, or drop the second.

The Malay and Chinese are a first translation that uses the glossary's words ("berhenti makan"
and "停" as in the visit questions' "Ask {doctor} about stopping {medicine}", and "how you
feel"). They are awaiting a native speaker's pass, as the rest of the catalogue is.

## Sign-off

| # | Adviser | Date | Outcome |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
