/** `GET /profiles/{id}/feed` — confirmed against the running dev server's `/openapi.json`. */

export interface FeedItem {
  itemId: string;
  type: string;
  supply: string;
  status: string;
  renderedFromState: string;
  language: string;
  format: string;
  headline: string;
  body: string[];
  voice: string[];
  why: Record<string, unknown>;
  priority: number;
  capsClass: string;
  scope: string;
  deliverTo: string;
  autoplay: boolean;
  sourceId: string | null;
  cite: Record<string, unknown> | null;
  boundary: string | null;
}

export interface FeedResponse {
  audience: string;
  items: FeedItem[];
}
