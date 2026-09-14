"""Safety: the rules that sit under reasoning, not on top of it.

`high_risk` is the label-photo rule for a high-risk drug (docs/medications-module.md §9,
E16-04): a dose of one is saved from a label photo, never from a message or a voice note
alone. It is a hook on the memory store, so it holds whichever surface writes the fact — the
review card (E02), which names the drug, and the medicines module (E04), which carries the
registry's class on the line; one table, one refusal (`HighRiskNeedsLabelPhoto`) for both.

`plain_words` is the verifier behind `make plain-words` (docs/plain-words.md, E22-01): every
string tagged `@patient` passes the standard or does not ship, and `plain_words.verify` is the
same check for the memos and cards the backend writes at run time.

`red_flags` is the list of the things we do not wait for (docs/smart-nudges.md §2, E21): a
`Flag` raised on the SYMPTOM event a word was said in, before any ranking or cap, telling
every live key with the emergency scope; a flag that depends on a fact not on the record is
written with why it was suppressed, so the caregiver sees it was considered. The same module
holds the words (E19-05): a table the WhatsApp thread reads free text against, in three
languages, and the escalation ladder written beside a flag raised there.

The boundary copy arrives with its own story.
"""
