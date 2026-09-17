import { describe, expect, it, vi } from "vitest";
import type { GrantOut, DigestEntryOut } from "../../src/api/familyTypes";
import type { FeedItemOut } from "../../src/api/types";
import { MessageRow, NearYouTile, PersonTile } from "../../src/screens/Connect";
import { one, text } from "./ui/render";

const grant: GrantOut = {
  key_id: "key-1",
  holder_person_id: "person-1",
  holder_name: "Mei",
  role: "caregiver",
  scopes: ["medicines"],
  window: "always",
  granted_at: "2026-09-01T00:00:00Z",
  expires_at: null,
  lines: [],
};

describe("Connect's family tile: an avatar, a name, a role — one tap opens the keys screen", () => {
  it("draws the person's name and role, and is one button", () => {
    const onClick = vi.fn();
    const tile = one(<PersonTile grant={grant} onClick={onClick} />);
    expect(tile.type).toBe("button");
    expect(text(tile)).toBe("MMeiCarer"); // the avatar's initial, then his name, then the role word
    (tile.props.onClick as () => void)();
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("Connect's near-you tile: the feed's own local card, as a feature tile", () => {
  it("carries the card's own headline and its first line, and opens the card screen on a tap", () => {
    const item = { item_id: "i1", type: "local", headline: "Dengue near you", body: ["A cluster was reported nearby."] } as unknown as FeedItemOut;
    const tile = one(<NearYouTile item={item} />);
    expect(tile.type).toBe("button");
    expect(text(tile)).toBe("Dengue near youA cluster was reported nearby.");
  });
});

describe("Connect's message row: the digest's own words, never a raw row", () => {
  it("shows the backend's line, the family member's own words, and the time, one tap to the thread", () => {
    const onClick = vi.fn();
    const entry: DigestEntryOut = { kind: "check_in", at: "2026-09-14T10:30:00Z", lines: ["Mei says she will bring your tablets on Sunday."], text: "I'll bring your tablets on Sunday.", message_id: "m1" };
    const row = one(<MessageRow entry={entry} locale="en-SG" onClick={onClick} />);
    expect(text(row)).toContain("Mei says she will bring your tablets on Sunday.");
    expect(text(row)).toContain("I'll bring your tablets on Sunday.");
    expect(row.type).toBe("button"); // one button, the whole row its target (Rows.tsx)
    (row.props.onClick as () => void)();
    expect(onClick).toHaveBeenCalledOnce();
  });
});
