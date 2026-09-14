"""Reasoning: what Nura works out from the record, always as patterns to discuss, never a finding.

Nothing here diagnoses or treats, and nothing here calls a model to decide pharmacology.

`ranges` is the port the lab trend reads reference ranges through (`ReferenceRanges`), with the
fixture table behind it until a licensed one is signed off. `trends` is the lab trend (E09-01):
a series of confirmed facts, each against the range that fits him on the day, the direction
over the last three in arithmetic, and the lines he reads — the number, the range, where it
sits when the range is the lab's own, the direction, and the boundary line naming the doctor.
No line names a cause or a treatment (`.claude/rules/safety.md`).

The visit loop (`visits`, E05) prepares a person for seeing the doctor and writes down what the
doctor said, in his words, through the plain-words verifier.
"""
