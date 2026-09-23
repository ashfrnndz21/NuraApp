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
 * memory only here — `lib/api`'s own concern, not a screen's; C1 wires a
 * persisted copy (secure storage) once the sign-in screen exists.
 */
let sessionToken: string | null = null;

export function setSessionToken(token: string | null): void {
  sessionToken = token;
}

export function getSessionToken(): string | null {
  return sessionToken;
}
