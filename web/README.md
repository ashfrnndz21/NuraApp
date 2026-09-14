# Nura — the web client

The app the patient opens in Safari and adds to the home screen (ADR 0001). TypeScript in
strict mode, Preact with signals, Vite, CSS custom properties, Vitest for units, Playwright
for the phone-sized end-to-end flow. No UI framework beyond Preact, no CSS framework.

```sh
make web         # dev server on http://127.0.0.1:5173/app/ (proxies /api to make dev); --host for the phone
make build-web   # web/dist, which make dev then serves at http://127.0.0.1:8000/app/
make web-test    # Vitest: strings, refusal map, proud number, Today model, contrast
make web-e2e     # Playwright against the built app the backend serves (needs make dev)
npm run plain-words   # the backend's verifier over web/src/strings/*.ts only
```

## Layout

- `src/ui/tokens.css` — docs/design-system.md §2 as custom properties; the two densities are
  `data-density="patient|caregiver"` on `<html>`, the wash is `data-posture`.
- `src/strings/{en,ms,zh}.ts` — every patient-facing line, each under a `// @patient [kind]`
  tag the backend's verifier reads (`app.safety.plain_words.strings_in_typescript`).
  `refusals` maps every refusal class name to one plain sentence.
- `src/api/` — `client.ts` (bearer header, `/api` base, the `{"refusal": …}` shape as a
  `Refused` error, one call at a time), `nura.ts` (one function per route), `types.ts`.
- `src/store/` — `kv.ts` (IndexedDB), `session.ts` (token, profile, language, density).
- `src/flow.ts` — which screen is up and the doors logic. `src/screens/` — one file per step.
- `src/today/` — the Now card, the greeting, the State and tablets cards, the proud number.
- `src/speech/speak.ts` — `speak(card)`: the one seam for the spoken twin.
- `src/sw/sw.ts` — the service worker; `src/offline/` — its registration and the Today cache.

## Design decisions

**Token storage.** The bearer token lives in memory and in IndexedDB, never in a cookie.
The API authenticates by the `Authorization` header alone, so a cookie would add nothing
but a value the browser attaches to every request to the origin — `/docs`, static files,
anything — and a cross-site request surface to defend. IndexedDB is per origin, survives
the home-screen app being closed, is not sent anywhere, and is cleared by sign-out. The
same store keeps the chosen profile, the device's language and look, and the last Today
page, so the app reopens on the Now card with no network.

**API serving: one origin.** The backend serves every route both at the root and under
`/api` (one router included twice), and serves `web/dist` at `/app` when
`NURA_WEB_DIST` names it. The client only ever calls `/api/...` on its own origin: no CORS,
no cookies, and the service worker can tell the shell (cached) from health data (never
cached, by path). In dev Vite serves the source at `:5173/app/` and proxies `/api` to
`:8000` by one rule; the built app is what the phone will get from the deployment.

**Requests one at a time.** `api()` queues calls. A person does one thing at a time, and the
local SQLite database refuses two requests that each read and then write their audit line
concurrently; the queue costs milliseconds and makes the laptop behave like the deployment.

**Speech.** `speak(card)` reads the card's lines with the Web Speech API in en-SG, ms-MY or
zh-CN. It is called from the Hear button and from nowhere else — never on load, never when
the next card appears. The backend's pre-rendered voice is a later adapter set with
`setSpeaker`; nothing else changes.

**Consent words from the API.** `GET /consent/wording` hands the client today's words and
their version, so the yes on the for-me door is for exactly what was shown and no client
carries a copy of the wording that could drift.

**Densities.** The owner of the papers gets the patient density (20px body, 56px targets,
paper under every card); anyone holding a key gets the caregiver density (16px, glass
first). The person can override it under Me; the choice is per device.

**The proud number.** Days on which a Taken landed — counted from the medicines trail when the
key can read it, and from this phone's own memory of its taps otherwise — and never lower
than the number the phone has already shown. Not a streak: a quiet day takes nothing away.

**Offline.** The worker precaches the shell on install (the Vite plugin in `vite.config.ts`
lists the built files into it) and answers navigations from the cache when the network is
gone. It never caches `/api`. The app keeps the last Today page per profile in IndexedDB and
renders it first, then the fresh one if it can — there is no spinner either way.

**Dev vs build.** The worker is only registered from the build (Vite does not build it in
dev), so `make web` is for working on screens and the offline behaviour is proven against
`make dev` serving `web/dist`. Over plain http on a LAN address the browser will not
install a worker or offer "add to home screen" — that needs https, which the cloud
deployment brings; on the Mac, `127.0.0.1` counts as secure.
