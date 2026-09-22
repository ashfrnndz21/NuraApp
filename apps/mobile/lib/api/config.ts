/**
 * `lib/api` is a typed client over Nura's own FastAPI backend
 * (`backend/app/channels/api`) — nothing moves to another backend
 * (mobile-architecture.md §2). For the Home spike every call below is
 * a stub returning the same shape the real route answers with, so
 * pointing `baseUrl` at a running backend and flipping `mode` to
 * `"live"` is the entire swap — no caller changes.
 */
export const apiConfig = {
  mode: 'demo' as 'demo' | 'live',
  baseUrl: process.env.EXPO_PUBLIC_NURA_API_URL ?? 'http://localhost:8000',
};
