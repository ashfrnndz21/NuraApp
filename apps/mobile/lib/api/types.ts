/** Shapes mirrored from `backend/app/channels/api` (health_tab.py, feed.py, medicines.py). */

export interface HealthOverviewResponse {
  headline: string;
  insight: {
    title: string;
    date: { day: string; month: string };
    body: string;
    cta: string;
  };
}

export interface FeedTodayItem {
  id: string;
  kind: 'document' | 'reminder' | 'media';
  title: string;
  subtitle: string;
  cta?: string;
}

export interface MedicationReminderResponse {
  label: string;
  medicineName: string;
  dueAt: string;
}

export interface MedicineSummary {
  plain: string;
  real: string;
  prescriber: string;
}
