import { askFixtureAnswer, bloodTest, eveningReminder, healthInsight, homeHeadline } from '../../features/home/mock';
import { apiConfig } from './config';
import type { FeedTodayItem, HealthOverviewResponse, MedicationReminderResponse } from './types';

async function liveGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiConfig.baseUrl}${path}`);
  if (!res.ok) throw new Error(`Nura API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

/** `GET /{profile_id}/health/overview` — the greeting, headline and primary insight. */
export async function getHealthOverview(profileId: string): Promise<HealthOverviewResponse> {
  if (apiConfig.mode === 'live') return liveGet(`/profiles/${profileId}/health/overview`);
  return { headline: homeHeadline, insight: healthInsight };
}

/** `GET /{profile_id}/feed/today` — the ranked cards below the insight. */
export async function getFeedToday(profileId: string): Promise<FeedTodayItem[]> {
  if (apiConfig.mode === 'live') return liveGet(`/profiles/${profileId}/feed/today`);
  return [
    { id: 'blood-test-12-sep', kind: 'document', title: bloodTest.title, subtitle: bloodTest.subtitle, cta: bloodTest.cta },
  ];
}

/** `GET /{profile_id}/medication-reminder` — the next dose due. */
export async function getMedicationReminder(profileId: string): Promise<MedicationReminderResponse> {
  if (apiConfig.mode === 'live') return liveGet(`/profiles/${profileId}/medication-reminder`);
  return { label: eveningReminder.label, medicineName: eveningReminder.medicine, dueAt: '21:00' };
}

/**
 * `POST /profiles/{id}/runs` (ADR 0019 §5 — not yet built on the
 * backend). In demo mode the composer talks to the fixture emitter in
 * `lib/ai/events.ts` directly, which already emits this exact event
 * shape; this stub exists so the swap point is visible and typed.
 */
export async function startNuraRun(profileId: string, intent: string) {
  if (apiConfig.mode === 'live') {
    throw new Error('POST /profiles/{id}/runs is not built yet (ADR 0019 §5) — stay in demo mode.');
  }
  return { runId: `demo_${profileId}_${intent}`, fixture: askFixtureAnswer };
}
