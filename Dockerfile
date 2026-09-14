# syntax=docker/dockerfile:1
# Nura's production image (docs/deploy.md). Three stages: the web client built with Node 20;
# the backend's dependencies installed from backend/requirements.lock, every one pinned; and
# the runtime, which holds only the venv, the backend's code, its migrations, the fixture
# answers a demo runs on, and the web build. One uvicorn process serves the API at / and
# /api and the web client at /app. It runs as a non-root user and carries no dev flag: a dev
# run (NURA_DEV_CODE_SENDER, NURA_FROZEN_CLOCK) is a laptop's, and the process refuses to start
# on the fixtures unless NURA_DEMO_MODE=1 (ADR 0008). Migrations are the platform's release
# step, `alembic upgrade heads` in this image, before the new version takes traffic.

FROM node:20-bookworm-slim AS web
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY backend/requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/nura \
    && /opt/nura/bin/pip install --no-deps -r /tmp/requirements.lock \
    && /opt/nura/bin/pip check

FROM python:3.12-slim-bookworm
RUN groupadd --system --gid 10001 nura \
    && useradd --system --uid 10001 --gid nura --no-create-home --home-dir /srv \
       --shell /usr/sbin/nologin nura
COPY --from=deps /opt/nura /opt/nura
WORKDIR /srv/backend
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
# The answers the fixture providers read (paper, visits, voice, feed, WhatsApp, drugs, lab
# ranges). They are served only on a demo; the tests themselves are not in the image.
COPY backend/tests/fixtures ./tests/fixtures
COPY --from=web /src/web/dist /srv/web/dist
ENV PATH=/opt/nura/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NURA_WEB_DIST=/srv/web/dist \
    PORT=8000
USER nura
EXPOSE 8000
# --proxy-headers: the platform terminates https in front of this process.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
