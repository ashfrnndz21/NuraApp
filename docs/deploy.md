# Deploying Nura — Singapore, one container, one Postgres

This is the runbook for putting Nura where a phone can reach it over https: checkpoint 19 in
`docs/checkpoints.md`. It covers one region, Singapore. Malaysia is a second deployment with
its own database and bucket; nothing is shared across the two (`docs/trust/pdpa-data-map.md`
§5).

**Render is the recommended platform for the demo.** Nothing needs installing on the laptop:
the Blueprint in `render.yaml` creates the web service and a Render Postgres, both in Singapore,
from the dashboard. For the demo, artefact bytes stay on the instance's own disk: that is
acceptable for a demo only, and a deployment with real data needs a Singapore-only bucket.
Fly.io (`fly.toml`, region `sin`) is the alternative; it needs its `flyctl` command. Neither needs
Docker or Postgres on the laptop: the image builds on the platform, and Postgres is the
platform's.

The long-term home is still AWS (`docs/build-plan.md` §2: Aurora PostgreSQL in ap-southeast-1
and ap-southeast-5, `infra/`). This deployment is how the web client reaches a phone before
that stack exists. It runs the same container and the same migrations.

---

## 1. What is deployed

- **One container.** Its image is the repo's `Dockerfile`:
  - the web client, built with Node 20
  - the backend, on the pinned dependencies in `backend/requirements.lock`
  - one uvicorn process: the API at `/` and `/api`, the web client at `/app`

  It runs as a non-root user with no dev flags, and CI builds it on every pull request (the
  `image` job).
- **One Postgres, in Singapore.** The release step runs `alembic upgrade heads` before a new
  version takes traffic. The `backend-postgres` CI job runs every migration up, down and up
  again, and runs the whole test suite on Postgres 16.
- **One place for artefact bytes, in Singapore.** That is a bucket (Fly: Tigris; or AWS S3 in
  ap-southeast-1). A demo may use the instance's own disk instead (Render, below).
  - **The largest thing stored is a consult recording**: up to 48 MiB, sent on Stop as its
    own bytes (`audio/webm`) in one request.
    - The app refuses anything larger (`MAX_CONSULT_BYTES`), and nothing in front of it sets a
      lower limit: uvicorn has none.
    - The bucket store gives each request two minutes.
    - Check the platform's own request-size limit allows 48 MiB before recording a visit
      over https.
- **Health checks.**
  - `GET /health/ready` answers 200 when the process is up and the database answers, and 503
    when it does not. Both platforms gate traffic on it.
  - `GET /health` only says the process is up.
  - `GET /api/deployment` says the region and whether this is a demo.

## 2. What cannot be real yet, and why the first deployment is a demo

Every provider that reaches the outside world is a fixture today. It answers from the files in
`backend/tests/fixtures/`, which the image carries. Each fixture refuses to start on a process
that is neither a laptop's dev run nor a declared demo (`app/fixtures.py`, ADR 0008).

| Provider | Today | What makes it real | Refuses outside a dev run or demo |
|---|---|---|---|
| Login code sender (SMS / email) | Logs the code (dev run); sends nothing and takes the operator's code (demo) | An SMS provider in the region, an email sender | yes |
| WhatsApp | Fixture sandbox: sends into memory | A business solution provider on Meta's Cloud API, approved templates, the region's number | yes |
| Drug data (identification, interactions, dosing) | A dozen medicines from `tests/fixtures/drugs` | A licensed drug-data client (build-plan §3) | yes |
| Reference ranges for lab trends | Fixture table | A signed-off licensed table | yes |
| Photo / PDF / handwriting reader (OCR, vision) | Answers only for the fixture papers | Textract and a vision model in the region | yes |
| Visit summariser | Answers only for the fixture transcripts | A model endpoint in the region | yes |
| Speech (voice notes) | Answers only for the fixture recordings | A speech provider in the region | yes |
| Speaker separation (who spoke when in a consult recording) | Answers only for the fixture recordings | A diarisation model in the region | yes |
| Voice (a card said aloud, E11) | Silence as long as the lines | A speech provider in the region | yes |
| App push (E11) | Reaches nobody (`NoDevices`) | A push sender (APNs / web push) | yes: a demo reaches nobody, and a real deployment refuses to start until one is built |
| Feed searcher and compressor | Fixture pages and summaries | The allowlisted fetcher and a grounded model call | yes |
| Calendar | Real: an uploaded `.ics` is read in memory (the fixture calendar is tests-only) | — | yes (for the fixture) |
| Ask retriever | Real: keyword retrieval (the fixture retriever is tests-only) | — | yes (for the fixture) |
| Object store | A directory on disk (laptop, demo) | A bucket in the region: built (`app/ingestion/s3.py`) | yes, the directory store |

So a deployment without `NURA_DEMO_MODE=1` does not start today. That is intended: the line
comes out when the last fixture has a real adapter.

**A demo (`NURA_DEMO_MODE=1`, ADR 0008)** is the only way to run on the fixtures anywhere but
a laptop:

- **The banner.** Every screen carries "Demo — not for real health information", and so does
  the printable emergency card.
- **Test numbers only.** Only the reserved test range is accepted: `+65 0xxx xxxx`, a Singapore
  number no phone can have. Any real number anywhere in a request is refused.
- **Sign-in.** Nobody is sent a code. A test number signs in with the operator's code,
  `NURA_DEMO_LOGIN_CODE`.
- **The nightly wipe.** Everything is wiped each night at 03:00 Singapore time.
- **No dev features.** The frozen clock and the `/dev/…` routes stay off.

## 3. Settings

Every setting comes from the environment, and every secret from the platform's secret store:
`fly secrets set …`, or Render's environment page and Blueprint prompts. Nothing secret is in
the repo, `fly.toml` or `render.yaml`.

| Variable | Secret | Demo (this runbook) | A real deployment | Notes |
|---|---|---|---|---|
| `NURA_REGION` | no | `SG` | `SG` (or `MY` for Malaysia's) | Required. The one region this process serves. |
| `NURA_DATABASE_URL` | **yes** | the platform's Postgres URL | the same | Required. `postgres://…` and `?sslmode=` are accepted as the platform gives them. Use the direct URL, not a pooled (PgBouncer) one. |
| `NURA_DEMO_MODE` | no | `1` | **absent** | ADR 0008. |
| `NURA_DEMO_LOGIN_CODE` | **yes** | six digits you choose | **absent** (refused) | Required with demo mode. Give it only to the people you invite. |
| `NURA_OBJECT_BUCKET_URL` | no | Fly: `https://fly.storage.tigris.dev/<bucket>` | the region's bucket, e.g. `https://<bucket>.s3.ap-southeast-1.amazonaws.com` | A bucket in Singapore. |
| `NURA_OBJECT_BUCKET_REGION` | no | `auto` (Tigris) | `ap-southeast-1` | The bucket's signing region. |
| `NURA_OBJECT_ACCESS_KEY_ID` | **yes** | from the bucket | from the bucket | |
| `NURA_OBJECT_SECRET_ACCESS_KEY` | **yes** | from the bucket | from the bucket | |
| `NURA_OBJECT_STORE` | no | Render demo only: `/tmp/nura-objects` | **absent** (refused) | A directory store. The night's wipe empties it and a restart loses it. |
| `NURA_PAPER_FIXTURES`, `NURA_VISIT_FIXTURES`, `NURA_VOICE_FIXTURES`, `NURA_FEED_FIXTURES`, `NURA_WHATSAPP_FIXTURES`, `NURA_SPEAKER_FIXTURES` | no | `tests/fixtures/paper`, `…/visits`, `…/voice`, `…/feed`, `…/whatsapp`, `…/speakers` | absent once real adapters exist | Set in `fly.toml` / `render.yaml`. |
| `NURA_WHATSAPP_DEV_SECRET` | **yes** | a long random string | **absent** | The fixture's webhook secret. Render generates it. |
| `NURA_WHATSAPP_PROVIDER` | no | unset (`fixture`) | the real provider's name, once built | |
| `NURA_WHATSAPP_NUMBER` | no | unset | the region's business number, E.164 | |
| `NURA_DRUG_REGISTRY`, `NURA_REFERENCE_RANGES` | no | unset (`fixture`) | the licensed source's name, once built | |
| `NURA_WEB_DIST` | no | set by the image (`/srv/web/dist`) | the same | |
| `PORT` | no | `8000` (Fly, in `fly.toml`); Render sets its own | the same | |
| `NURA_DEV_CODE_SENDER` | — | **must be absent** | **must be absent** | A laptop's dev run: it prints login codes. It is refused alongside demo mode. |
| `NURA_FROZEN_CLOCK` | — | **must be absent** | **must be absent** | Refused outside a dev run. |

The process refuses to start, with the missing or forbidden setting named, if any of these
holds:
- a required setting is missing
- `NURA_DEMO_LOGIN_CODE` is not six digits
- demo mode and a dev run are declared together
- a fixture would run without demo mode

## 4. First deploy on Render (recommended for the demo)

No local tool is needed. You create the account.

1. Open **New → Blueprint** in the dashboard, connect the GitHub repository
   `ashfrnndz21/NuraApp`, and choose the branch.
2. Render reads `render.yaml`. It shows one web service (`nura-sg`, Docker, Singapore) and one
   Postgres (`nura-sg-db`, Singapore, reachable only inside Render). It asks for
   `NURA_DEMO_LOGIN_CODE`: enter six digits. It generates `NURA_WHATSAPP_DEV_SECRET` itself.
3. Choose **Apply**. The database is created, the image builds, and the pre-deploy command
   (`alembic upgrade heads`) migrates. The service takes traffic once `/health/ready` answers.
   The pre-deploy command needs a paid instance; the Blueprint asks for `starter`.
4. Check it with `https://nura-sg.onrender.com/health/ready` and `/api/deployment`, as above.

Render has no bucket of its own, so the demo keeps artefact bytes on the instance's disk
(`NURA_OBJECT_STORE=/tmp/nura-objects`). The night's wipe empties it, and a restart or
redeploy loses it, which is acceptable for a demo only. A real deployment on Render sets the
`NURA_OBJECT_BUCKET_*` values to a bucket in Singapore and removes `NURA_OBJECT_STORE`.

`autoDeploy` is off: deploy from the dashboard (**Manual Deploy**). Roll back from the
service's **Events** page.

## 5. First deploy on Fly.io (the alternative)

You create the account (the operator cannot). Install `flyctl`, the platform's one command
(<https://fly.io/docs/flyctl/install/>), then sign in with `fly auth login`. From the repo root:

1. **Create the app.** Its name is the one in `fly.toml`; change both if the name is taken.

       fly apps create nura-sg

2. **Create the Postgres in Singapore.** Run `fly mpg create` and choose Singapore (`sin`).
   - If Singapore is not offered to your organisation, **stop**. The database must not be
     created in another region. Use Render instead, or a Postgres you already hold in
     Singapore.
   - Copy the **direct** connection string, not the pooled one.

       fly secrets set NURA_DATABASE_URL='postgres://…'

3. **Create the bucket, then set its values** under Nura's names:

       fly storage create

   It prints the bucket name and its keys. Then:

       fly secrets set NURA_OBJECT_BUCKET_URL=https://fly.storage.tigris.dev/<bucket> \
         NURA_OBJECT_ACCESS_KEY_ID=<AWS_ACCESS_KEY_ID> NURA_OBJECT_SECRET_ACCESS_KEY=<AWS_SECRET_ACCESS_KEY>

   In the bucket's settings, add a lifecycle rule that expires objects after one day. That is
   the demo's nightly wipe for bytes.

4. **Set the demo's secrets:**

       fly secrets set NURA_DEMO_LOGIN_CODE=<six digits> NURA_WHATSAPP_DEV_SECRET=<a long random string>

   `python3 -c "import secrets; print(f'{secrets.randbelow(10**6):06d}', secrets.token_urlsafe(32))"`
   prints one of each.

5. **Deploy:**

       fly deploy

   The image builds on Fly's builders. The release command migrates the database. The new
   machine takes traffic once `/health/ready` answers.

6. **Check it.** Run `curl https://nura-sg.fly.dev/health/ready`, which answers `{"status":"ok"}`.
   Then run `curl https://nura-sg.fly.dev/api/deployment`, which answers
   `{"region":"SG","demo":true}`.

Later deploys are `fly deploy`. To roll back, run `fly releases`, then
`fly deploy --image <an earlier image>`. A migration is forward-only on deploy; stepping one
back is by hand: `fly ssh console -C "alembic downgrade <revision>"`.

## 6. Running the checkpoints against the https address

The checkpoint walker is a client. It speaks only HTTP, so it runs against the deployment
from the laptop, with the demo's code instead of a server log. It then takes its numbers from
the test range.

    cd backend
    NURA_BASE_URL=https://nura-sg.fly.dev NURA_DEMO_LOGIN_CODE=<the code> python3 -m scripts.checkpoint 2

`make checkpoint N=2` works the same with the two variables set.

- **Can run against the demo:** 2, 3, 4, 5, 6, 14, 16, 17, 18 and 21. Each was walked against a
  local demo-mode server before this runbook was written.
- **Cannot:** 7, 8, 9, 13 and 15. Each takes a step through a route only a laptop's dev run
  has:
  - 7, 8 and 13 pretend the hour on the feed with `?at=`
  - 9 uses the WhatsApp dev routes
  - 15 moves the frozen clock

  Walk those against `make dev`.

What a walk creates stays until 03:00 Singapore time.

## 7. Opening it on the phone

- **iPhone.** Open `https://<the address>/app/` in Safari. Tap **Share**, then **Add to Home
  Screen**.
- **Android.** Open it in Chrome and choose **Install app** (or **Add to Home screen**) from the
  menu.

The home-screen app opens on its own, with no browser bar. The demo banner is at the top of
every screen.

To sign in, type a test number: `+65 0` followed by seven digits, for example `+65 0000 0001`.
Type any name, then the demo code where the app asks for the code from the message. Two
people signing in with two different test numbers see two different accounts.

## 8. Region, and what never leaves it

- Postgres, the bucket and the container are all in Singapore. Nothing replicates to another
  region, and no analytics vendor is configured.
- The app keeps no access log (`--no-access-log`). The platform's own request logs and metrics
  are the platform's; where they are kept, and for how long, is an open question on the PR.
  URLs carry profile ids, never names or numbers.
- Before real health information, each of these must be true:
  - every fixture above has a real adapter in the region
  - `NURA_DEMO_MODE` is removed
  - the data protection officer is named
  - the breach tabletop has been run (`docs/trust/pdpa-data-map.md` §6–7)
  - the bucket and the platform are confirmed to keep data in Singapore
  - the platform's request logs are checked: where they are kept and for how long
  - the platform accepts a 48 MiB request, the largest recording of a visit
