"""Smart nudges (E17-03, E11-07): generated from how he is this week, handed to delivery.

`engine.plan_nudges` works out the day's nudges from State and the record — anticipation,
check-in, pattern, commitment, recognition, presence — ranks them, applies the rules (one a
day, never at night, none on a day with a red flag, a kind he ignored twice rests for a week)
and returns `NudgeDraft`s. `engine.hand_over` writes the chosen one down and gives it to
delivery (`handoff.deliveries`); nothing here sends anything. `metrics` counts what he did
with them, and with the feeling cloud, for the owner and the chief.
"""
