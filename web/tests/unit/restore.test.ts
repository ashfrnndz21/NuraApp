import { describe, expect, it } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { afterRestoreFailure } from "../../src/restore";

describe("reopening the app", () => {
  it("goes back to sign-in only when the session itself is refused", () => {
    expect(afterRestoreFailure(new Refused("NoSession", 401))).toBe("signin");
    expect(afterRestoreFailure(new Refused("HttpError", 401))).toBe("signin");
  });

  it("stays on Today for a lost network, a server error or any other refusal", () => {
    expect(afterRestoreFailure(new Unreachable())).toBe("stay");
    // What CI met: /me answered 500 while the page before the reload was still writing.
    expect(afterRestoreFailure(new Refused("HttpError", 500))).toBe("stay");
    expect(afterRestoreFailure(new Refused("OutOfScope", 403))).toBe("stay");
    expect(afterRestoreFailure(new Error("anything else"))).toBe("stay");
  });
});
