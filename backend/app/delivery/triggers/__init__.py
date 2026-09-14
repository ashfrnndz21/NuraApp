"""The trigger engine, the channels and caps, the escalation ladder (E00-05, E11-05, E11-06,
E11-10).

`models` holds the tables: `DeliverySettings` (what a profile changed of the defaults),
`Delivery` (one row per attempt to reach one person, with the rule that fired) and `Ladder`
(an unanswered action climbing Dad → helper → caregiver on duty → chief). `rules` says what
each trigger is — kind, type, scope, channels, cap, quiet hours — and the clock of his day.
`deliver` is where every trigger ends: the checks, the channel list, the row, the SHARE.
`ladder` climbs, and holds `escalate_flag`, the one door a red flag is escalated through.
`engine.run_due(profile, at)` evaluates everything due for one profile at one moment; it has
no scheduler of its own (the deployment's cron calls it; see `engine`).
"""
