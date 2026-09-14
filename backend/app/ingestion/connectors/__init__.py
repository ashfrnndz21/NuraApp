"""Read-only connectors (E18): the calendar first.

`calendar` is the port a calendar is read through (`CalendarSource`) — read, never written —
with a fixture and a minimal RFC 5545 reader behind it. `models` holds the `Connector` (one
per profile and kind, resting on its own consent) and the `AppointmentProposal` a matching
event becomes. `service` connects, scans, and turns a person's yes into a planned visit.
docs/read-only-connectors.md is the design: purpose-bound, shown before stored, third
parties dropped, nothing leaves, nothing trains anything.
"""
