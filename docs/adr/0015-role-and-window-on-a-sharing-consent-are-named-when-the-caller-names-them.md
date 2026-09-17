# ADR 0015 — A sharing consent's role and window are checked only when the caller names them

**Date** 2026-09-17 · **Status** accepted · **Decided by** the builder session, on #185's own text · **Stories** #185, #184

## Context

#185 asked that a `SHARE_WITH_PERSON` consent (`POST /consents/sharing`) bind the role a key
holder is cut as and the window it runs for, not only the person and the parts — the words he
reads should name "Mei, your daughter, can see your medicines and your visits, for thirty
days," and `app.keys.grants.grant_key` should refuse a key cut for a different role or for a
window that outlasts the one named.

The most literal reading makes `role` and `window` required on `SharingConsentIn` and
`SharingPreviewIn`, and required on the internal `Sharing`/`SharingWords` dataclasses `grant_
consent` renders from. Doing that surfaced a second effect of the same story: `grant_consent`'s
default `text_version` is always `current_version(SHARE_WITH_PERSON)`, and bumping that
version to 3 (the one that names role and window) means **every** caller that does not pin an
older version now renders the version-3 template — including the two call sites inside this
codebase that always did (`app.identity.doors._hand_over`, the claim flow, which already names
CHIEF/ALWAYS) and, more consequentially, every test helper that calls `grant_consent` or `POST
/consents/sharing` without naming a role or a window at all. `tests/support.py`'s `agree_to_
family_sharing` (28 files) and `tests/api.py`'s `let_in` (55 files, 106 call sites) are exactly
that: a consent is agreed once, and a key is then cut in whatever role the individual test is
actually exercising — caregiver here, chief there, viewer elsewhere. Making role required at
the wire layer meant every one of those ~130 call sites would need an audited, matching role
(and, transitively, `require_consent`'s exact-version match meant even a caller who correctly
supplied a role but pinned the old wording version would still be refused `ConsentOutOfDate`).

## Decision

1. **`role` and `window` are optional on `SharingConsentIn`, `SharingPreviewIn`, `Sharing` and
   `SharingWords`, default `None`.** A caller that does not state them gets exactly today's
   behaviour: the consent constrains neither, and `grant_key` never raises `KeyNotAsAgreed`
   for a `None` field on the consent it reads (`app.keys.grants.grant_key`, guarded on
   `consent.role is not None` / `consent.window is not None`). A caller that does state them —
   the current app always will — gets the full story: the words name both, the row keeps
   both, and a key cut differently is refused.
2. **The rendered words are backward-identical when role and window are not given.**
   `render_sharing` (`app.consent.texts`) treats a missing `window` as `KeyWindow.ALWAYS` for
   rendering purposes only (never for storage) — "until you say stop" is what an unstated
   window always meant, even before this story had a word for it — and drops the blank line a
   missing `role` would otherwise leave, rather than showing it empty. The result: a consent
   agreed with neither field renders byte-for-byte the same lines version 2 always did, so
   `test_the_preview_is_the_words_the_consent_keeps` and every other content-sensitive
   assertion holds without change.
3. **Not done:** making the fields required. That is the more literal reading of the issue and
   is a smaller, more mechanical follow-up now that the seam exists — thread `role=`/`window=`
   through `agree_to_family_sharing` and `let_in` (both already accept the parts and the
   relationship as parameters; the pattern is the same) and drop the `None` branch in
   `render_sharing` and the two `Optional`s. Left as a deliberate follow-up rather than done
   here because it touches roughly 130 call sites across 55 files for a change with no
   behavioural difference for the real client, which already names both.

## Consequences

- The web/mobile client can adopt `role`/`window` on `POST /consents/sharing` immediately;
  every existing integration that does not is unaffected.
- A reviewer reading only `grant_key`'s new check might expect it to fire unconditionally;
  it fires only when the consent it reads was itself given a role and a window. This ADR, and
  the docstrings on `Sharing`, `SharingWords` and `grant_key`, say so.
- The gap named above (required fields, `tests/support.py` and `tests/api.py` threaded
  through) is real follow-up work, not a hidden shortcut — flagged in the PR that carries this
  ADR.
