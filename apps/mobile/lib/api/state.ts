import { http } from './httpClient';
import { apiConfig } from './config';
import type { ProfileState } from '../../domain/profileState';

interface ProfileStateWire {
  state_id: string;
  profile_id: string;
  sequence: number;
  computed_at: string;
  posture: 'stable' | 'watch' | 'act';
  trigger: { kind: string; fact_id: string | null };
  supersedes_id: string | null;
  stale: boolean | null;
  stale_after: string | null;
  dimensions: Record<string, unknown>;
  withheld: { dimensions: string[]; scopes: string[] };
  boundary: string;
  word: string;
  line: string;
  drivers: { key: string; [k: string]: unknown }[];
}

/**
 * `GET /profiles/{id}/state` — Home's own driver (C4). Consumed as a
 * `STATE_SNAPSHOT` on first load and `STATE_DELTA` thereafter, when read
 * through the run event stream; this plain GET is for a cold load before
 * any run has started.
 */
export async function getProfileState(profileId: string): Promise<ProfileState> {
  if (apiConfig.mode === 'demo') {
    throw new Error('getProfileState: demo mode has no fixture yet — use STATE_SNAPSHOT off the run stream instead.');
  }
  const w = await http.get<ProfileStateWire>(`/profiles/${profileId}/state`);
  return {
    stateId: w.state_id,
    profileId: w.profile_id,
    sequence: w.sequence,
    computedAt: w.computed_at,
    posture: w.posture,
    trigger: { kind: w.trigger.kind, factId: w.trigger.fact_id },
    supersedesId: w.supersedes_id,
    stale: w.stale,
    staleAfter: w.stale_after,
    dimensions: w.dimensions,
    withheld: w.withheld,
    boundary: w.boundary,
    word: w.word,
    line: w.line,
    drivers: w.drivers,
  };
}
