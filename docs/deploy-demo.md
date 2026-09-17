# Deploying the demo — quickstart

The full runbook, the settings table and the reasoning behind every choice are in
`docs/deploy.md`. This page is the short version for the one path this repo is set up for
today: Render, Singapore, the demo (`NURA_DEMO_MODE=1`, ADR 0008), checkpoint 19. It changes
nothing on its own — `render.yaml` only prepares the configuration; someone with a Render
account presses **Apply**.

## 1. Create the Blueprint

1. In the Render dashboard: **New → Blueprint**, connect `ashfrnndz21/NuraApp`, pick the
   branch this was merged to.
2. Render reads `render.yaml` and shows one web service (`nura-sg`, Docker, Singapore) and
   one Postgres (`nura-sg-db`, Singapore, reachable only from the web service).
3. It asks for the secrets below before it will let you Apply.

## 2. The secrets to enter

| Secret | Where it comes from |
|---|---|
| `NURA_DEMO_LOGIN_CODE` | Choose any six digits. This is the code everyone you invite types to sign in — give it to them directly, never post it publicly. |
| `NURA_VAPID_PUBLIC_KEY`, `NURA_VAPID_PRIVATE_KEY`, `NURA_VAPID_SUBJECT` | Optional, all three together or none. Generate a pair with the one-line script in `docs/deploy.md` §3. `NURA_VAPID_SUBJECT` is a `mailto:` address or an `https://` page — whoever a push service should contact about these pushes. Leave all three blank to skip Web Push; the demo still runs, it just reaches nobody with a push (`NoDevices`). |
| `NURA_ANTHROPIC_API_KEY` | Your Anthropic API key, from the Anthropic console. Asked for up front so it is ready in Render's secret store; it sits unused until you turn on a Claude feature (§5 below). Leave it blank if you don't plan to. |

`NURA_WHATSAPP_DEV_SECRET` is not asked for — Render generates it itself
(`generateValue: true` in `render.yaml`). Everything else the demo needs (region, fixture
paths, the object store directory) is already set as plain configuration in `render.yaml`,
not a secret, because none of it identifies anyone or grants access to anything.

## 3. Apply

Choose **Apply**. Render creates the database, builds the image, then runs the pre-deploy
command, `alembic upgrade heads`, against the new database before the service takes any
traffic. The service starts taking traffic once `/health/ready` answers 200.

## 3a. Seed a living record: Pa and Mei

Set `NURA_DEMO_SEED=1` (plain configuration in `render.yaml`, not a secret) and the demo
opens onto a living record from the moment it first serves, instead of an empty one. At
startup — and again every morning after the 03:00 wipe (ADR 0008) empties the tables —
`app.demo_seed.seed_demo` creates two people, idempotently, through the same services every
real sign-up writes through (`grant_consent`, `grant_key`, the medicines and readings
services, `audited_write`, under Pa's own key), so the audit trail, consents and scopes are
exactly what they would be for a real family:

- **Pa** (`+65 0000 1111`) owns the profile. He has four medicines with a dose taken today —
  his blood pressure tablet, his cholesterol tablet, his sugar tablet, and warfarin, which is
  high-risk and carries its label photo; a blood pressure book with two weeks of readings; one
  visit ten days ago with a memo ("Every evening, eat a lighter dinner.") and one booked a
  week from now; a note that he is tired; two papers, a hospital discharge letter and the
  warfarin label; his area (Ang Mo Kio); and a week's dose history on the sugar tablet, so the
  count reads 12 of 14.
- **Mei** (`+65 0000 2222`) holds a chief key: every scope, the same window as any chief's.

A Malaysian deployment (`NURA_REGION=MY`) seeds the same two people on Malaysian numbers
(`+60000011111` and `+60000022222`) instead.

Given without `NURA_DEMO_MODE=1` or a declared dev run, the process refuses to start — the
same gate every other fixture on this deployment is held to.

On the Welcome screen, under **Get started**, two more buttons show whenever the deployment
answers `demo` or `dev` on `GET /deployment`: **Try it as Pa** and **Try it as Mei**, which
sign in at once, no phone number or code typed. They never show on a deployment without
`NURA_DEMO_SEED=1`, and never on one that is neither a demo nor a dev run.

`docs/checkpoints.md` still walks its own accounts on top of whatever `NURA_DEMO_SEED` seeded
— each checkpoint registers fresh numbers of its own, so the two never collide. Walking
checkpoints 2–6, 14, 16–18 and 21 against a fresh deploy is still how the rest of the demo
gets exercised end to end (see §4).

## 4. Verify

    curl https://nura-sg.onrender.com/health/ready       # {"status":"ok"}
    curl https://nura-sg.onrender.com/api/deployment      # {"region":"SG","demo":true}

Then, on a phone or in a browser: open `https://nura-sg.onrender.com/app/`, sign in with a
test number (`+65 0` followed by seven digits, e.g. `+65 0000 0001`) and the
`NURA_DEMO_LOGIN_CODE` you entered, and check "Demo — not for real health information" is at
the top of the screen.

To check more than that it boots, run the checkpoints that are allowed to walk against a
deployment (the rest step through dev-only routes and stay laptop-only — `docs/deploy.md`
§6, `docs/checkpoints.md`):

    cd backend
    NURA_BASE_URL=https://nura-sg.onrender.com NURA_DEMO_LOGIN_CODE=<the code> \
      python3 -m scripts.checkpoint 2   # then 3, 4, 5, 6, 14, 16, 17, 18, 21

## 5. Turning on Claude features

`NURA_EXTRACTOR`, `NURA_SEARCHER` and `NURA_COMPRESSOR` are not set in `render.yaml`, so each
defaults to `fixture` — the demo reads papers, searches the feed and compresses results from
the files in `backend/tests/fixtures/` only, the same as a laptop. That is the safer default
for a first deploy: it needs no key, it cannot send anything anyone types to a third party,
and it is what every checkpoint in `docs/checkpoints.md` was written and walked against.

Each of the three has a Claude-backed adapter (`app.ingestion.claude_extract.ClaudeExtractor`
and `app.delivery.feed.claude_adapters`) that only builds on a declared demo (ADR 0017): a
laptop dev run cannot turn it on, only a deployment with `NURA_DEMO_MODE=1`, because
Anthropic's first-party API does not process in Singapore or Malaysia and a demo is the one
deployment where nothing shown to it claims to be a real family's data. To turn one on:

1. Make sure `NURA_ANTHROPIC_API_KEY` is set (§2) — without it the adapter refuses to build.
2. In the Render dashboard, on the `nura-sg` service's **Environment** tab, add
   `NURA_EXTRACTOR=claude` (the photo/PDF reader), `NURA_SEARCHER=claude` and
   `NURA_COMPRESSOR=claude` (the feed's search and compression) — any one on its own, or all
   three.
3. Save; Render redeploys the service with the new setting. No migration runs.

Turning one off is deleting that line, the same way.

## What this does not cover

- A second country (Malaysia) is a second Blueprint, its own database — see `docs/deploy.md`
  §1.
- Object storage here is the instance's own disk (`NURA_OBJECT_STORE`), emptied by the
  nightly wipe and lost on every restart or redeploy — acceptable for a demo only. Real data
  needs a Singapore-only bucket (`docs/deploy.md` §2, §5).
- `NURA_PRIVACY_CONTACT` is set on a laptop's `make dev` but nothing in `backend/app` reads
  it yet — there is no wired-up "stop this in one tap" address to configure here. It is not
  in `render.yaml` because setting it would promise something the running app does not do.
- Rolling back, Malaysia, and the bucket setup for real data are all in `docs/deploy.md`,
  not repeated here.
