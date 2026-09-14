"""Onboarding (E01): the profile's settings, the health biography and the first week.

`settings` is the settings screen (E01-03): conditions from the fixed graph in
`conditions.json`, language, density, what helps him read, hear and remember, his name, his
doctor's name and his breakfast time — a row superseded on every save, and facts State folds.
`biography` is the one sitting in which his papers become the record (E01-02): a state machine
over the settings, the papers (through the capture path, E02), a read-back of what was
understood, the questions the papers raised (`gaps`) and a summary. `plan` is the first week
(E01-04): one prompt a day from tomorrow at breakfast for what the biography did not capture,
done when it arrives by any route. `strings` holds every word he reads while this happens and
`words` checks each filled line against docs/plain-words.md before it is served.

Importing this package wires the first week's eager close onto the memory store: a fact that
fills a gap closes its prompt in the same unit of work (`plan.close_prompts_on_fact` on
`app.memory.semantic.after_fact_write`), the way State's recompute is wired by `app.state`.
"""

from __future__ import annotations

from app.memory import semantic
from app.onboarding.plan import close_prompts_on_fact

if close_prompts_on_fact not in semantic.after_fact_write:
    semantic.after_fact_write.append(close_prompts_on_fact)
