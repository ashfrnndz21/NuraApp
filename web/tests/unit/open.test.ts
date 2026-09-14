import { describe, expect, it, vi } from "vitest";
import type { DayNudgesOut, FeedItemOut } from "../../src/api/types";
import { resolveOpen, takeOpen } from "../../src/push/open";

const ID = "3f2c7a10-8b4e-4c1d-9a2f-1e5d6c7b8a90";
const card = { item_id: ID, headline: "Your blood pressure today" } as unknown as FeedItemOut;
const nudges = { day: "2026-09-14", nudges: [], withheld: 0 } as DayNudgesOut;

describe("what a push opens", () => {
  it("reads ?open= once and takes it out of the address", () => {
    const history = { replaceState: vi.fn() };
    expect(takeOpen({ search: `?open=${ID}&x=1`, pathname: "/app/", hash: "" }, history)).toBe(ID);
    expect(history.replaceState).toHaveBeenCalledWith(null, "", "/app/?x=1");
  });

  it("nothing to open, or not an id, is null", () => {
    const history = { replaceState: vi.fn() };
    expect(takeOpen({ search: "", pathname: "/app/", hash: "" }, history)).toBeNull();
    expect(history.replaceState).not.toHaveBeenCalled();
    expect(takeOpen({ search: "?open=../me", pathname: "/app/", hash: "" }, history)).toBeNull();
  });

  it("a card by its id is the card", async () => {
    const opened = await resolveOpen(ID, { feedItem: async () => card, dayNudges: async () => nudges });
    expect(opened).toEqual({ kind: "card", item: card });
  });

  it("a card refused or missing falls back to Today, after the day's nudges", async () => {
    const dayNudges = vi.fn(async () => nudges);
    const opened = await resolveOpen(ID, {
      feedItem: async () => {
        throw new Error("NoSuchItem");
      },
      dayNudges,
    });
    expect(opened).toEqual({ kind: "today" });
    expect(dayNudges).toHaveBeenCalledOnce();
  });

  it("even with no network at all, Today", async () => {
    const fail = async () => {
      throw new Error("offline");
    };
    expect(await resolveOpen(ID, { feedItem: fail, dayNudges: fail })).toEqual({ kind: "today" });
  });
});
