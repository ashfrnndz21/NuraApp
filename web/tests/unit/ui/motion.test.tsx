import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { pendingSignal } from "../../../src/api/client";
import { PendingCard } from "../../../src/ui/kit";
import { all, byTestId, hasClass, one } from "./render";

/** The motion and waiting-states pass (docs/design/motion.md): motion shows real state, never
 *  fakes time. These tests hold the API client's own pending count and the kit's Skeleton to
 *  that — a request key going pending draws the Skeleton, going idle draws the real content, and
 *  nothing here, or anywhere in `ui/kit`, waits on a clock of its own. */

const UI_DIR = fileURLToPath(new URL("../../../src/ui", import.meta.url));
const KIT_DIR = join(UI_DIR, "kit");

describe("PendingCard: pending -> Skeleton -> content, in the card's own shape", () => {
  it("stands the kit Skeleton in place of the content while its key is pending", () => {
    pendingSignal("motion-test-a").value = 1;
    const el = one(
      <PendingCard requestKey="motion-test-a" testId="card">
        <p data-testid="body">real content</p>
      </PendingCard>,
    );
    expect(hasClass("pending-skeleton")(el)).toBe(true);
    expect(byTestId("card-skeleton")(el)).toBe(true);
    expect(all(el, byTestId("body"))).toEqual([]);
    pendingSignal("motion-test-a").value = 0;
  });

  it("draws the real content, wrapped for its entrance, the instant nothing is pending under the key", () => {
    pendingSignal("motion-test-b").value = 0;
    const el = one(
      <PendingCard requestKey="motion-test-b" testId="card">
        <p data-testid="body">real content</p>
      </PendingCard>,
    );
    expect(hasClass("card-enter")(el)).toBe(true);
    expect(byTestId("card")(el)).toBe(true);
    expect(all(el, byTestId("body")).length).toBe(1);
  });

  it("two calls sharing a key: the Skeleton stands until the count is really back to zero, not after the first settles", () => {
    pendingSignal("motion-test-c").value = 2;
    expect(hasClass("pending-skeleton")(one(<PendingCard requestKey="motion-test-c">x</PendingCard>))).toBe(true);
    pendingSignal("motion-test-c").value = 1;
    expect(hasClass("pending-skeleton")(one(<PendingCard requestKey="motion-test-c">x</PendingCard>))).toBe(true);
    pendingSignal("motion-test-c").value = 0;
    expect(hasClass("card-enter")(one(<PendingCard requestKey="motion-test-c">x</PendingCard>))).toBe(true);
  });

  it("one key's pending count never shows another key's Skeleton", () => {
    pendingSignal("motion-test-d1").value = 1;
    pendingSignal("motion-test-d2").value = 0;
    expect(hasClass("card-enter")(one(<PendingCard requestKey="motion-test-d2">x</PendingCard>))).toBe(true);
    pendingSignal("motion-test-d1").value = 0;
  });
});

describe("prefers-reduced-motion collapses every motion token, and the shimmer, to instant", () => {
  const tokens = readFileSync(join(UI_DIR, "tokens.css"), "utf8");
  const base = readFileSync(join(UI_DIR, "base.css"), "utf8");
  const warm = readFileSync(join(UI_DIR, "warm.css"), "utf8");

  it("--settle, --press and --wash-fade all go to 0ms under reduced motion", () => {
    const block = tokens.slice(tokens.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toMatch(/--settle:\s*0ms/);
    expect(block).toMatch(/--press:\s*0ms/);
    expect(block).toMatch(/--wash-fade:\s*0ms/);
  });

  it("the one global rule every kit animation relies on: no animation runs at all, for anything, under reduced motion", () => {
    const block = base.slice(base.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toMatch(/animation:\s*none\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0ms\s*!important/);
  });

  it("names the skeleton's shimmer and the thinking dots' pulse specifically, not only the generic rule", () => {
    const block = warm.slice(warm.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toMatch(/\.thinking-dots i/);
    expect(block).toMatch(/\.skeleton-bar/);
    expect(block).toMatch(/\.trace-spin/);
  });
});

describe("no animation in ui/kit runs on a timer without a real state change (grep test)", () => {
  it("no ui/kit source file calls setTimeout to fake a wait — every wait is a signal or a real prop", () => {
    const files = readdirSync(KIT_DIR).filter((name) => name.endsWith(".ts") || name.endsWith(".tsx"));
    expect(files.length).toBeGreaterThan(0);
    for (const name of files) {
      const text = readFileSync(join(KIT_DIR, name), "utf8");
      expect(text, `${name} uses setTimeout for a wait; motion must answer a real state change, never a clock of its own`).not.toMatch(/setTimeout\s*\(/);
    }
  });
});
