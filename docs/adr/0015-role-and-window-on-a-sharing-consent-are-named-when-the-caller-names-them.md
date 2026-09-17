# ADR 0015 — A sharing consent's role and window are required, not optional

**Date** 2026-09-17 · **Status** accepted (superseding an earlier, rejected draft of this ADR) ·
**Decided by** the operator, overriding the builder session's first attempt · **Stories** #185, #184

## Context

#185 asked that a `SHARE_WITH_PERSON` consent (`POST /consents/sharing`) bind the role a key
holder is cut as and the window it runs for, not only the person and the parts — the words he
reads should name "Mei, your daughter, can see your medicines and your visits, for thirty
days," and `app.keys.grants.grant_key` should refuse a key cut for a different role or for a
window that outlasts the one named.

**First attempt, rejected.** The builder session's first pass made `role` and `window`
optional everywhere — `SharingConsentIn`, `SharingPreviewIn`, and the internal `Sharing`/
`SharingWords` dataclasses — reasoning that making them required would force every one of the
~130 test call sites across 55 files that agree to sharing and then cut a key (`tests/
support.py::agree_to_family_sharing`, `tests/api.py::let_in`) to name a matching role, since
`grant_consent`'s default `text_version` always renders the current wording, and the current
wording (version 3) is the one that names role and window.

That reasoning was sound about the mechanical cost and wrong about the conclusion. Optional at
the API boundary meant the *real client never had to send them* — and it didn't:
`web/src/api/family.ts`'s `SharingBody`, used by both `previewSharing` and `letSomeoneIn`, had
no `role` or `window` field. So every consent given through the actual Family screen was
unconstrained, exactly as before #185, and the story's own acceptance line — "his yes should
bind the role and the window" — was unmet for any real family. The enforcement existed only in
tests that deliberately exercised it. A binding the real client never sends is no binding.

## Decision

1. **`role: KeyRole` and `window: KeyWindow` are required, no default**, on `SharingConsentIn`,
   `SharingPreviewIn`, and the internal `Sharing` and `SharingWords` dataclasses
   (`app.consent.service`). Omitting either from `POST /consents/sharing` or its preview is a
   422 at the door. `render_sharing` (`app.consent.texts`) no longer has an `Optional` branch:
   every `SHARE_WITH_PERSON` consent, at the current wording, names the role and the window in
   the words, full stop.
2. **The web client sends both.** `web/src/screens/family/Keys.tsx`'s `NewKey` already has a
   role picker (`ROLES`) and a window picker (`WindowChoices`) and already discards a stale
   preview when either changes (`choose()` for role, `changed(setWindow)` for window, both
   already bumping the same `generation` counter the parts and the person do) — it only needed
   to actually put `role`/`window` on the wire, in `asked()`. `web/src/screens/onboarding/
   Invite.tsx`'s gap has no picker at all: it always invites a caregiver, for `ALWAYS` (the
   same fixed shape `nura.cutKey` already hardcoded), so its `asked()` states that fixed pair
   rather than offering a choice.
3. **Every test call site now states a role.** `agree_to_family_sharing` takes `role: KeyRole`
   required and `window: KeyWindow = KeyWindow.ALWAYS` (window has a safe default — `ALWAYS` is
   never "outlasted" by a narrower key, so only tests that specifically exercise a shorter
   window need to override it; role has none, since `KeyNotAsAgreed` checks exact identity).
   `let_in` (`tests/api.py`) takes the same shape at the HTTP/string level. Every call site
   across the suite was threaded to match whatever role the same holder's key is actually cut
   as right after — done by hand, file by file (not delegated: a delegated pass at this size
   was interrupted mid-way by an unrelated session stop and left the work half-finished, which
   is its own lesson). A few tests that agreed once and then cut two different roles for the
   same holder (`test_keys.py`) now agree twice, once per role, before each key cut — the new
   rule working as intended, not a workaround.
4. **A real mismatch, not just a missing field, turned up in the process:**
   `test_state_api.py`'s local `_key()` helper hardcodes `"role": "caregiver"` in the key-cut
   body it always sends; an earlier pass had given the paired `let_in()` call `role="helper"`,
   misreading a `HELPER` *scopes list* constant as if it named the role. Both now say
   `caregiver`. This is exactly the class of bug `KeyNotAsAgreed` exists to catch — it just
   needed the enforcement to actually be reachable to catch it.
5. **`RoleWindowNeedCurrentWording` stands, and matters more now.** Found by the
   clinical-safety reviewer before role/window were made required: `SharingConsentIn.
   wording_version` is independently settable, and `grant_consent` allows an older version for
   capturing a past agreement. Since role and window are now always given, this refusal is what
   stops every `SHARE_WITH_PERSON` consent from silently being pinnable to a wording version
   that never actually said what role or window it was recording.

## Consequences

- `POST /consents/sharing` and its preview are a breaking change for any caller that does not
  send `role`/`window` — by design. There is no such caller left: the web client sends both,
  and every test does too, verified by a full multi-line scan of every
  `agree_to_family_sharing(`/`let_in(`/`Sharing(` call site in `tests/`.
- `test_sharing_role_window.py::test_role_and_window_are_required_to_let_someone_in` and
  `test_family_api.spec.ts` (`web/tests/e2e`, added alongside this decision) both go through
  the *real* request shape — the Pydantic schema and the actual web client code, respectively —
  and prove a key cut for a different role, or a longer window, than the one agreed is refused.
  That is the test the first attempt's own reviewer said would have caught the gap; it now
  exists on both ends of the wire.
- A `SHARE_WITH_PERSON` consent can now only ever be recorded at the current wording version
  (see point 5): capturing one at an older version, a capability `text_version` still offers
  other purposes, is not offered here any more. Consistent with role and window now always
  being part of what is agreed, and what the older wording never said.
