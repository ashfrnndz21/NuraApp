/**
 * `lib/api` is a typed client over Nura's own FastAPI backend
 * (`backend/app/channels/api`) — nothing moves to another backend
 * (mobile-architecture.md §2). `mode: 'live'` calls the real routes;
 * `'demo'` (the Home-spike default while screens are still being built)
 * returns the same shapes from `features/home/mock.ts`. Flipping `mode`
 * is the entire swap — no caller changes (section 42).
 *
 * `baseUrl` defaults to this builder's own dev server (port 8061, never
 * 8000 — the owner's live copy). `EXPO_PUBLIC_NURA_API_URL` overrides it
 * for a phone on the tunnel.
 *
 * That dev server needs one variable of its own for this web target to
 * reach it at all: `NURA_MOBILE_DEV_CORS=1` (`backend/app/settings.py`).
 * Metro's web bundle has no same-origin proxy the way `web/`'s Vite dev
 * server does, so the browser calls the API cross-origin, and only a
 * server started with that flag answers a browser's CORS preflight
 * (loopback origins only, never credentials). It is deliberately not
 * folded into `NURA_DEV_CODE_SENDER` — that one is also set in CI's web
 * job and on the owner's own backend, neither of which run this Expo
 * target, and the CORS middleware's `Vary: Origin` header defeats the
 * web app's service-worker cache on an offline run that never needed
 * it. `NURA_MOBILE_DEV_CORS=1` is the one variable the Expo target
 * needs beyond `make dev`'s own defaults.
 */
export const apiConfig = {
  /**
   * The golden path (section 38 Phase 2) runs live, against this
   * builder's own dev server — the whole point of this checkpoint is a
   * real backend, not a fixture stub (C0's own instruction: "the
   * fixture runner... must be replaced by this client"). `'demo'`
   * remains available for a screen or a test that explicitly wants it.
   */
  mode: 'live' as 'demo' | 'live',
  baseUrl: process.env.EXPO_PUBLIC_NURA_API_URL ?? 'http://localhost:8061',
};

/**
 * The session token from `/auth/phone/verify` or `/dev/quick-signin`
 * (`Authorization: Bearer <token>`, `deps.py`'s `_bearer`). Held in
 * memory only, on purpose, for now — a hard reload (or a cold app start)
 * loses it and the person re-signs in (`sign-in.tsx`/`who.tsx` handle
 * that path already). FIX BEFORE MERGE, independent review of PR #332:
 * this comment previously promised a persisted copy "once the sign-in
 * screen exists" — that screen has existed since C1 and this is still
 * in-memory only; corrected here rather than left stale. Persisting it
 * (`expo-secure-store`, native-only — Keychain/Keystore, with a web
 * fallback still to design) is real, not-yet-done work, not a line this
 * file can claim for free.
 */
let sessionToken: string | null = null;

export function setSessionToken(token: string | null): void {
  sessionToken = token;
}

export function getSessionToken(): string | null {
  return sessionToken;
}

/**
 * The profile this session is looking after — set once by `who.tsx` (the
 * owner's own new profile, an existing one recognised via `ProfileAlreadyOwned`,
 * or a `for-someone` profile), read by every screen after it that needs
 * a `{profile_id}` and has no route param carrying one. In-memory only,
 * same lifetime as `sessionToken`.
 */
let currentProfileId: string | null = null;

export function setCurrentProfileId(id: string | null): void {
  currentProfileId = id;
}

export function getCurrentProfileId(): string | null {
  return currentProfileId;
}
