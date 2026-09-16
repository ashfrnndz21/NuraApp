# ADR 0008 — Demo mode: a deployment on the fixtures, and it says so

**Date** 2026-09-15 · **Status** accepted · **Decided by** the operator

## Context

ADR 0001 puts Nura on the phone as a web app served over https, so the backend needs to run
somewhere other than a laptop. Today every provider that reaches the outside world is a
fixture:

- the login code sender
- WhatsApp
- licensed drug data
- the reference ranges
- the photo and PDF reader
- the visit summariser
- speech
- the feed's searcher and compressor

Each fixture answers from files in `backend/tests/fixtures/`. None of them can carry real
health information safely. The drug fixture knows a dozen medicines. The paper reader only
knows the photos it was written for. The code sender prints codes to a log.

Until now they had one guard: a process refused to start on them unless it was a declared dev
run (`NURA_DEV_CODE_SENDER=1`). That guard also turns on things no public server may have:
- login codes printed to the log
- a frozen clock (`NURA_FROZEN_CLOCK`)
- the `/dev/…` routes

The code sender, the WhatsApp provider and the clock checked for a dev run. The drug registry,
the reference ranges, the extractor, the transcriber, the summariser, the searcher and
compressor, and the local object store did not: they started wherever their setting was
present.

The owner wants to open Nura on his phone over https before the real providers exist
(`docs/checkpoints.md`, row 19). That needs a deployment that may run on the fixtures and
cannot be mistaken for the real thing.

## Decision

`NURA_DEMO_MODE=1` is a second, separate declaration. A process that is not a laptop may run on
the fixtures only with it. A demo holds six promises, each enforced in code and tested in
`backend/tests/test_demo_mode.py`:

1. **It says so on every screen.** `GET /deployment` answers `{"region": "SG", "demo": true}`.
   The web client asks at start, remembers the answer for offline use, and shows the banner
   first on every screen: "Demo — not for real health information", then "This is a demo. Do
   not put real health information in it. Everything here is wiped each night." It appears in
   English, Malay and Chinese, and passes `docs/plain-words.md`. The printable emergency card
   prints the same banner first, so a printed demo card cannot pass for a real one. The API's
   own page is titled as a demo.
2. **No real phone number is accepted.** Only the reserved test range is taken: `+65 0xxx xxxx`
   (Singapore) and `+60 0…` (Malaysia). Neither country gives a subscriber number beginning
   with 0, because in both 0 is the trunk prefix that E.164 drops, so no number in the range
   reaches a real phone. This is enforced twice:
   - The demo code sender refuses any other number before a login challenge is written.
   - `DemoNumbersOnly`, in front of every route, refuses any JSON body that carries a
     real-looking number anywhere in it (403, `NotInTheDemo`). That covers a helper's number,
     a patient set up for by phone, and a WhatsApp sender, including on routes written after
     today.

   Email sign-in is refused, because no email could carry the link.
3. **Nobody is sent a code, and none is logged.** A test number signs in with the operator's
   code, `NURA_DEMO_LOGIN_CODE`: six digits kept in the platform's secret store, which he
   gives to the people he invites. This is how test phone numbers work in hosted
   phone-login services, and it keeps the demo closed to people without the code.

   The trade-off, accepted because nothing real is in a demo: anyone holding the code can sign
   in as any test number, so what is in the demo is visible to everyone the operator invited.
4. **It forgets every night.** At 03:00 on the region's wall clock, every row of every table
   is emptied. The schema stays, and so does alembic's version table. A local object
   directory is emptied too. A bucket expires its objects by its own lifecycle rule
   (`docs/deploy.md`).

   The check runs before the app serves and every five minutes after (`app.demo.wipe_if_due`).
   No marker is kept: the wipe is due when an account or a login request is older than the
   last 03:00, so the data is its own record of the last wipe. A machine asleep at 03:00
   wipes when it wakes, before its first answer.
5. **It is not a dev run.** `NURA_DEMO_MODE=1` with `NURA_DEV_CODE_SENDER=1` refuses to start.
   The frozen clock and every `/dev/…` route stay off. A demo never prints a login code.
6. **Where fixtures may run is decided in one place.** Every fixture class is marked
   `@fixture`. `create_app` refuses any of them unless the process is a dev run or a
   demo (`app.fixtures.check_fixtures`). A test walks `app/` for every class named `Fixture…`
   and fails if one lacks the mark (`tests/test_fixture_refusals.py`). The drug registry, the
   reference ranges, the extractor, the transcriber, the summariser, the searcher and
   compressor, and the local object store now refuse outside a dev run or demo, as the code
   sender and WhatsApp already did.

## Consequences

- **The first https deployment is a demo** (`fly.toml` and `render.yaml` set
  `NURA_DEMO_MODE=1`). A non-demo deployment cannot start until every fixture has a real
  adapter behind its port. That is the intent: removing the one line is the last step of
  replacing the fixtures, not a shortcut past it.
- **Most checkpoints can run against the demo** over https, with `NURA_BASE_URL` and
  `NURA_DEMO_LOGIN_CODE`. The walker then draws its numbers from the test range and uses the
  operator's code instead of reading a log. Checkpoints that step on a dev-only route cannot:
  7 and 8 (a feed step pretends the hour with `?at=`), 9 (the WhatsApp dev routes), 13
  (`?at=`) and 15 (it moves the frozen clock with `/dev/clock`). They stay laptop checkpoints.
  Walked against a local demo-mode server, checkpoints 2–6, 14, 16–18 and 21 pass; 7 stops, as it
  should, at `?at=` (`NotOnADevRun`).
- **Free text can still carry real information.** A person can type real words into a note or
  a question, and the banner and the test-number rule do not stop that. The nightly wipe
  limits how long anything stays, and the banner says why not to. A demo is not where a
  family's real record lives. The first family on real data waits for the real providers, the
  data protection officer and the breach tabletop (`docs/trust/pdpa-data-map.md` §6–7).
- **Some things are not built.** There is no rate limit on sign-in beyond each challenge's
  attempt count. The shared code has no rotation beyond the operator changing the secret.
  The operator accepted both, and the shared code itself, for demo mode only, because of what
  surrounds them: test numbers no phone can have (`+65 0…`, `+60 0…`), the banner on every
  screen, the nightly wipe, and no real data.
- **The sign-in message is in his language (#132), and on a demo it goes nowhere.** The demo
  sender is handed the finished message like any sender, and it neither sends nor logs it.
  No SMS path exists on a demo.

## Before real data

A demo holds none. Before a deployment holds real health information, as well as the real
providers, the data protection officer and the breach tabletop:

- **The bucket is Singapore-only.** Tigris and the instance's own disk are acceptable for the
  demo only, and Tigris only as a bucket created single-region in Singapore (`sin`): a Tigris
  bucket is Global by default (#161, docs/deploy.md).
- **The platform's request logs have been checked.** Where they are kept, and for how long,
  matters because URLs carry profile ids, though never names or numbers.
- **The platform accepts the largest request Nura sends.** That is a consult recording of up to
  48 MiB (#128). The app refuses anything larger, and nothing in the image sets a lower limit.
