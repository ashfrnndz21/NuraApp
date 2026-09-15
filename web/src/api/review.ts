import { api } from "./client";

/** The pharmacist's review queue (E22-04, ADR 0007), signed in with a staff token from the
 *  deployment's list — never a patient's session. Nothing here is anyone's record. */

export interface ReviewItemOut {
  item_id: string;
  kind: "card" | "source" | string;
  card_type: string | null;
  sample_number: number | null;
  source_id: string | null;
  language: string | null;
  /** A card's lines, de-identified before they were stored: headline, body, voice, why. */
  lines: { headline?: string; body?: string[]; voice?: string[]; why?: string; [key: string]: unknown };
  catalogue_ids: string[];
  verdict: "pending" | "approved" | "rejected" | "rewritten";
  reason: string | null;
  proposed: Record<string, unknown> | null;
  decided_by: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface TypeStatusOut {
  card_type: string;
  sampled: number;
  reviewed: number;
  pending: number;
  approved: number;
  rejected: number;
  rewritten: number;
  first_fifty_reviewed: boolean;
  flag: boolean;
}

export interface StatusOut {
  first: number;
  card_types: TypeStatusOut[];
  sources_pending: number;
}

export const reviewStatus = (staff: string) => api<StatusOut>("/review/status", { token: staff });

export const reviewQueue = (staff: string, verdict: "pending" | "any") => api<ReviewItemOut[]>("/review/queue", { token: staff, query: { verdict } });

export const approve = (staff: string, itemId: string, reason: string | null) =>
  api<ReviewItemOut>(`/review/items/${itemId}/approve`, { method: "POST", token: staff, body: { reason } });

export const reject = (staff: string, itemId: string, reason: string) =>
  api<ReviewItemOut>(`/review/items/${itemId}/reject`, { method: "POST", token: staff, body: { reason } });

export const rewrite = (staff: string, itemId: string, lines: { headline?: string; body?: string[] }, reason: string | null) =>
  api<ReviewItemOut>(`/review/items/${itemId}/rewrite`, { method: "POST", token: staff, body: { lines, reason } });
