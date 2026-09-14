"""Safety: the rules that sit under reasoning, not on top of it.

`high_risk` is the label-photo rule for a high-risk drug (docs/medications-module.md §9,
E16-04): a dose of one is saved from a label photo, never from a message or a voice note
alone. It is a hook on the memory store, so it holds whichever surface writes the fact — the
review card (E02), which names the drug, and the medicines module (E04), which carries the
registry's class on the line; one table, one refusal (`HighRiskNeedsLabelPhoto`) for both.

`plain_words` is the verifier behind `make plain-words` (docs/plain-words.md, E22-01): every
string tagged `@patient` passes the standard or does not ship, and `plain_words.verify` is the
same check for the memos and cards the backend writes at run time.

`boundary` is the boundary copy (E16-01): the register of inferring surfaces and the line each
carries, in every language. `recording` is the recording consent pattern (E16-02): the notice
spoken before a recording starts and `may_record`, the gate on the RECORDING consent.

`red_flags` is the list of the things we do not wait for (docs/smart-nudges.md §2), one
module and one table (`red_flag`): a word tapped on the feeling cloud (E21), free text on
WhatsApp (E19-05) and the words said or typed to the not-feeling-well button and the symptom
log (E13/E14) all raise the same `Flag` on the SYMPTOM event they were said in, before any
ranking or cap, telling every live key with the emergency scope; the words are one table
(`RED_FLAG_WORDS`, `detect`), in three languages. A flag that depends on a fact not on the
record is written with why it was suppressed, so the caregiver sees it was considered. The
button's flag is written through `write_flag_kept`, so a refusal later in the same request
cannot take it back, and the escalation ladder (`Escalation`) is written beside it.

`emergency_card`, `not_feeling_well` and `symptom_log` are E13/E14: the card a stranger is
handed, the one button, and how he feels in his words (ADR 0002). `people` is the two narrow,
audited reads of a Person row they make. They hear a voice note through the region-pinned
speech port, `app.ingestion.transcribe`.
"""
