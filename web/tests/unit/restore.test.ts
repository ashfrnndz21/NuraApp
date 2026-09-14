import { describe, expect, it } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { afterRestoreFailure, readFailure } from "../../src/restore";

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

describe("a failed read on Today", () => {
  it("keeps the page for a lost network or a server that could not answer", () => {
    expect(readFailure(new Unreachable())).toBe("network");
    expect(readFailure(new Refused("HttpError", 500))).toBe("server");
    expect(readFailure(new Refused("HttpError", 503))).toBe("server");
  });

  it("deletes it and says so for a refusal of the key", () => {
    expect(readFailure(new Refused("NoKey", 403))).toBe("refused");
    expect(readFailure(new Refused("OutOfScope", 403))).toBe("refused");
    expect(readFailure(new Refused("NoSession", 401))).toBe("refused");
  });
});
