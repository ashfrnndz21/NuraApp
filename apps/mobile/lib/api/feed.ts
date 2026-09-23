import { http } from './httpClient';
import { apiConfig } from './config';
import type { FeedItem, FeedResponse } from '../../domain/feed';

interface FeedItemWire {
  item_id: string;
  type: string;
  supply: string;
  status: string;
  rendered_from_state: string;
  language: string;
  format: string;
  headline: string;
  body: string[];
  voice: string[];
  why: Record<string, unknown>;
  priority: number;
  caps_class: string;
  scope: string;
  deliver_to: string;
  autoplay: boolean;
  source_id: string | null;
  cite: Record<string, unknown> | null;
  boundary: string | null;
}

interface FeedResponseWire {
  audience: string;
  items: FeedItemWire[];
}

function itemFromWire(w: FeedItemWire): FeedItem {
  return {
    itemId: w.item_id,
    type: w.type,
    supply: w.supply,
    status: w.status,
    renderedFromState: w.rendered_from_state,
    language: w.language,
    format: w.format,
    headline: w.headline,
    body: w.body,
    voice: w.voice,
    why: w.why,
    priority: w.priority,
    capsClass: w.caps_class,
    scope: w.scope,
    deliverTo: w.deliver_to,
    autoplay: w.autoplay,
    sourceId: w.source_id,
    cite: w.cite,
    boundary: w.boundary,
  };
}

/** `GET /profiles/{id}/feed` — the feed card(s) below Home's insight (C4). */
export async function getFeed(profileId: string): Promise<FeedResponse> {
  if (apiConfig.mode === 'demo') return { audience: 'demo', items: [] };
  const w = await http.get<FeedResponseWire>(`/profiles/${profileId}/feed`);
  return { audience: w.audience, items: w.items.map(itemFromWire) };
}
