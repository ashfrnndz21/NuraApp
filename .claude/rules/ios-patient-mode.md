---
paths:
  - "ios/Nura/**"
---
# iOS patient-mode constraints

- Vertical paging only in the feed; no horizontal gestures, no pull-to-refresh, no long-press, no swipe-to-dismiss. "Not for me" is a visible button.
- One action per card. 20pt body, 56pt targets, 7:1 contrast on any decision element. Decisions sit on the paper surface, never on glass.
- Never autoplay the next card. Audio starts only on tap.
- No badges, unread counts or streaks. The proud number only goes up.
- Dynamic Type through accessibility sizes; VoiceOver labels equal the spoken script; Reduce Motion disables all but opacity changes; works inside Assistive Access.
- Offline: today's list, the emergency card and the last feed page open with no network and no spinner.
