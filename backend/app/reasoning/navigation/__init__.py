"""Care navigation with drafted messages (T3).

From a real need already on the record — a check-up a letter names, a new medicine from the
pharmacy, a test coming up, a care-service category on Services — Nura drafts a short
plain-words message to the clinic or service, for him or his chief to send from their own
phone. Nura never sends anything itself: `app.reasoning.navigation.service.draft_message`
only ever returns text and a link built from the provider's own directory contact
(`sms:`/`https://wa.me/`); with no contact on file the draft is copyable only.

`needs.py` reads the record for a real need under its own scope (`RECORDS` for a letter's
follow-up date, `MEDICINES` for a new line, `VISITS` for an upcoming lab test or the
provider directory). `models.py` holds the shapes: `Need` (one real thing to draft for, with
its evidence), `Draft` (the drafted text, its links, who it speaks as). `rule_drafter.py` is
the catalogue-only drafter (`app/channels/strings.py`'s `TEXT`, under the plain-words paths),
en/ms/zh, filled only from the need's who/what/when/doctor — never a dose, never a diagnosis,
because no template slot exists for either. `app/llm/navigation_draft.py` holds the
Claude-backed drafter, gated by `app.llm.residency.allow_external_model` the same way every
other Claude-backed adapter is, and falls back to the rule draft on anything it cannot trust.
"""

from __future__ import annotations
