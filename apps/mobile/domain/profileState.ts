/** `GET /profiles/{id}/state` — confirmed against the running dev server's `/openapi.json`. */

export type Posture = 'stable' | 'watch' | 'act';

export interface StateDriver {
  key: string;
  [key: string]: unknown;
}

export interface ProfileState {
  stateId: string;
  profileId: string;
  sequence: number;
  computedAt: string;
  posture: Posture;
  trigger: { kind: string; factId: string | null };
  supersedesId: string | null;
  stale: boolean | null;
  staleAfter: string | null;
  /** Named dimensions (blood pressure, glucose, …) — kept as a bag, shaped per dimension by the caller. */
  dimensions: Record<string, unknown>;
  withheld: { dimensions: string[]; scopes: string[] };
  boundary: string;
  /** The one-word posture read (calm/watch/act, reader's own language). */
  word: string;
  /** The one-line summary Home's headline is built from. */
  line: string;
  drivers: StateDriver[];
}
