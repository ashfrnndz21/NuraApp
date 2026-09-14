"""The one base class for everything Nura declines to do."""

from __future__ import annotations


class Refusal(Exception):
    """Something a person asked for that Nura will not do.

    A refusal is meant to be shown, not swallowed: it says what was refused and never
    what was held back. Channels turn it into a sentence; nothing here writes copy.
    """
