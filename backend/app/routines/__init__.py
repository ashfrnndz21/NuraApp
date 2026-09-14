"""The day's routine (E10-01): set once, rendered to each person the way they read it.

`models` holds the `Routine` row — the clock times of his anchors, the readings he is
prompted for, the walks, when his Today page comes — immutable with supersession. `service`
sets it on a person's yes, reads it back with the dose schedule mapped onto the anchors from
the medicine lines (E04's dose codes), renders it per persona, and answers `due_now`.
"""
