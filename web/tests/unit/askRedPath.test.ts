import { describe, expect, it } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { askStartedTheRedPath } from "../../src/day/redPath";

describe("a question refused on the red-flag path", () => {
  it("is the emergency scope refused: the backend heard a red word this key may not raise", () => {
    expect(askStartedTheRedPath(new Refused("OutOfScope", 403, "emergency"))).toBe(true);
  });
  it("is nothing else: another scope, the server failing, or no network is Ask's own failure", () => {
    expect(askStartedTheRedPath(new Refused("OutOfScope", 403, "records"))).toBe(false);
    expect(askStartedTheRedPath(new Refused("HttpError", 500))).toBe(false);
    expect(askStartedTheRedPath(new Unreachable())).toBe(false);
    expect(askStartedTheRedPath(new Error("anything"))).toBe(false);
  });
});
