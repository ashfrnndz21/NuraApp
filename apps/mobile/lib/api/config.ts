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
