import { describe, expect, it, vi } from "vitest";
import type { FeedItemOut, ProviderOut, ProviderSummaryOut } from "../../src/api/types";
import { careCards, guideCards } from "../../src/feed/model";
import { CareBody, ClipMedia, GuideBody, NearYouBody } from "../../src/screens/tabs";
import { stringsFor } from "../../src/strings";
import { all, byTestId, byType, one, render, text } from "./ui/render";

const en = stringsFor("en");

/** A feed card with only the fields a test needs, the rest filled in so the type is honest —
 *  the same shape `GET /profiles/{id}/feed` sends. */
function card(overrides: Partial<FeedItemOut> & Pick<FeedItemOut, "type">): FeedItemOut {
  return {
    item_id: "item-1",
    supply: "today",
    status: "sent",
    rendered_from_state: "state-1",
    language: "en",
    format: "text",
    headline: "A card",
    body: ["A line."],
    voice: [],
    why: {},
    priority: 0,
    caps_class: "one",
    scope: "patient",
    deliver_to: "patient",
    autoplay: false,
    source_id: null,
    cite: null,
    boundary: null,
    day: "2026-09-14",
    created_at: "2026-09-14T02:00:00Z",
    expires_at: "2026-09-15T02:00:00Z",
    ...overrides,
  };
}

function provider(name: string, id = "prov-1"): ProviderSummaryOut {
  const out: ProviderOut = { provider_id: id, name, kind: "clinic", region: "SG", phone_e164: null, address: null };
  return { provider: out, visits: 2, last_visit: null, next_visit: null };
}

describe("Care services and Guides (Services tab)", () => {
  it("careCards keeps only the feed's LOCAL cards; guideCards keeps LEARNING and CLIP, nothing else", () => {
    const items = [
      card({ item_id: "a", type: "local" }),
      card({ item_id: "b", type: "learning" }),
      card({ item_id: "c", type: "clip" }),
      card({ item_id: "d", type: "seasonal" }),
      card({ item_id: "e", type: "story" }),
    ];
    expect(careCards(items).map((it) => it.item_id)).toEqual(["a"]);
    expect(guideCards(items).map((it) => it.item_id)).toEqual(["b", "c"]);
  });

  it("shows a local card with its why line, for the owner", () => {
    const local = card({ item_id: "local-1", type: "local", headline: "Haze near you", body: ["Keep your inhaler close."], why: { plain: "Because haze is high and you carry an inhaler." } });
    const nodes = render(<CareBody s={en} own name="" cards={[local]} providers={[]} dateOf={(iso) => iso} />);
    expect(text(all(nodes, byTestId("care-card")))).toContain("Haze near you");
    expect(text(all(nodes, byTestId("why")))).toBe("Because haze is high and you carry an inhaler.");
    expect(all(nodes, byTestId("care-empty"))).toEqual([]);
  });

  it("says the same thing about him by name, for a caregiver — and is silent about who he is when nothing local applies and he has no provider yet", () => {
    const nodes = render(<CareBody s={en} own={false} name="Pa" cards={[]} providers={[]} dateOf={(iso) => iso} />);
    expect(text(all(nodes, byTestId("care-empty")))).toBe("Nura has no local care service to show for Pa yet.");
  });

  it("the owner's own empty state names no one", () => {
    const nodes = render(<CareBody s={en} own name="" cards={[]} providers={[]} dateOf={(iso) => iso} />);
    expect(text(all(nodes, byTestId("care-empty")))).toBe("Nura has no local care service to show you yet.");
  });

  it("a provider on his record is not the empty state, even with no local card", () => {
    const nodes = render(<CareBody s={en} own name="" cards={[]} providers={[provider("Dr Tan, heart clinic")]} dateOf={(iso) => iso} />);
    expect(all(nodes, byTestId("care-empty"))).toEqual([]);
    expect(text(all(nodes, byTestId("care-provider")))).toContain("Dr Tan, heart clinic");
    expect(all(nodes, byTestId("care-providers-all"))).toHaveLength(1);
  });

  it("Guides is nothing at all when the feed has no learning card, never an empty tile", () => {
    expect(render(<GuideBody s={en} cards={[]} />)).toEqual([]);
  });

  it("a learning guide keeps its lines and its why, never a player", () => {
    const learning = card({ item_id: "guide-1", type: "learning", headline: "Understanding blood pressure", body: ["The top number is systolic."], why: { plain: "Because you take a blood pressure tablet." } });
    const nodes = render(<GuideBody s={en} cards={[learning]} />);
    expect(text(all(nodes, byTestId("guide-card")))).toContain("Understanding blood pressure");
    expect(text(all(nodes, byTestId("why")))).toBe("Because you take a blood pressure tablet.");
    expect(all(nodes, byTestId("clip-player"))).toEqual([]);
  });

  it("a clip card's poster is one button, and tapping it is what opens the player", () => {
    const onPlay = vi.fn();
    const poster = one(<ClipMedia s={en} playing={false} poster={null} video={null} onPlay={onPlay} />);
    expect(poster.props["data-testid"]).toBe("guide-play");
    expect(byType("button")(poster)).toBe(true);
    (poster.props.onClick as () => void)();
    expect(onPlay).toHaveBeenCalledOnce();
  });

  it("once playing, the player is on screen — the still until the excerpt arrives, then the video", () => {
    const withPoster = render(<ClipMedia s={en} playing poster="blob:still" video={null} onPlay={() => undefined} />);
    expect(all(withPoster, byTestId("clip-player"))).toHaveLength(1);
    expect(all(withPoster, byTestId("clip-poster"))).toHaveLength(1);
    expect(all(withPoster, byTestId("clip-video"))).toEqual([]);

    const withVideo = render(<ClipMedia s={en} playing poster="blob:still" video="blob:excerpt" onPlay={() => undefined} />);
    expect(all(withVideo, byTestId("clip-video"))).toHaveLength(1);
  });

  it("Near you is silent when Nura does not know the area, never a guess", () => {
    expect(render(<NearYouBody s={en} own name="" area={null} />)).toEqual([]);
  });

  it("Near you names his area, said about him by name for a caregiver", () => {
    const own = render(<NearYouBody s={en} own name="" area="Bedok" />);
    expect(text(all(own, byTestId("near-you")))).toBe("Nura knows your area is Bedok.");

    const other = render(<NearYouBody s={en} own={false} name="Pa" area="Bedok" />);
    expect(text(all(other, byTestId("near-you")))).toBe("Nura knows Pa's area is Bedok.");
  });
});
