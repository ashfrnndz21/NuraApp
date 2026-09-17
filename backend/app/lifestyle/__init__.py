"""Daily lifestyle logging: steps, heart rate, sleep, water and food intake.

Nothing new is stored here that the record does not already have a shape for. A metric he
logs is a Fact resting on a READING event, the same shape a typed blood pressure takes
(`app.channels.api.profiles.add_reading`); a meal he logs is a Fact resting on a FOOD event.
Both carry the same provenance and confidence conventions as every other fact: who entered
it, when, and how sure Nura is (always 1.0, `CONFIRMED_BY_PERSON`, for his own or a
key-holder's own word).

Automatic reading from a phone or watch is an external dependency Nura does not have yet
(docs/design-direction.md, "The one rule that changes the substance, not the look" and the
feature table's "Needs from outside" column). Nothing here builds it; the model already
carries the seam: `SourceChannel.DEVICE` exists on the event, so a device connector can write
the same shape later without a caller anywhere else changing.
"""

from __future__ import annotations
