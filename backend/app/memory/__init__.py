"""Memory: the three stores and the spine.

Episodic memory (`episodic`) holds the raw things that came in — an Artifact is a reference to
bytes kept in the profile's region, an Event is a moment something happened. Semantic memory
(`semantic`) holds Facts: statements about the profile, each with provenance and a confidence,
immutable, replaced only by supersession. Working memory (`working`) holds the Episode that is
going on now. Providers and Appointments (`spine`) are the timeline everything else hangs off.

Every row is the profile's, and every read and write goes through `app.audit.access`.
"""
