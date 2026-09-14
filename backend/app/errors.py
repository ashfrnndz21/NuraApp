"""The one base class for everything Nura declines to do."""

from __future__ import annotations


class Refusal(Exception):
    """Something a person asked for that Nura will not do.

    A refusal is meant to be shown, not swallowed: it says what was refused and never
    what was held back. Channels turn it into a sentence; nothing here writes copy.

    `written_down` is set by the audit trail once a line has been written for this refusal,
    so that a refusal passing through several doors on its way out leaves one line, not one
    per door.
    """

    written_down: bool = False
