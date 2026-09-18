import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import type { ReviewCardOut } from "../../src/api/types";
import { isPdf, PaperBatch, type BatchDeps } from "../../src/capture/batch";

/** Papers from his photos (E18-01): nothing sent before his yes; then one at a time, in order;
 *  every paper says what became of it; and nothing of a photo stays. */

function card(id: string, readable = true): ReviewCardOut {
  return {
    card_id: id,
    profile_id: "p1",
    artifact_id: `art-${id}`,
    document_kind: readable ? "lab_report" : "not_health",
    document_date: null,
    asked_as: null,
    source: null,
    notice: readable ? null : ["This page is not a health paper."],
    high_risk_class: null,
    created_at: "2026-09-14T02:00:00Z",
    confirmed_at: null,
    fields: readable ? [{} as ReviewCardOut["fields"][number]] : [],
  } as ReviewCardOut;
}

const file = (name: string, type = "image/png") => new File([`bytes of ${name}`], name, { type });

function rig(send: (file: File) => Promise<ReviewCardOut> = async (each) => card(each.name)) {
  let going = 0;
  let most = 0;
  const deps: BatchDeps = {
    thumb: vi.fn((each: File) => `blob:${each.name}`),
    revoke: vi.fn(),
    send: vi.fn(async (each: File) => {
      going += 1;
      most = Math.max(most, going);
      try {
        return await send(each);
      } finally {
        going -= 1;
      }
    }),
    readable: (each) => each.fields.length > 0,
  };
  return { batch: new PaperBatch(deps), deps, most: () => most };
}

describe("nothing goes before his yes", () => {
  it("picking many and leaving some out sends nothing", () => {
    const { batch, deps } = rig();
    batch.pick([file("a.png"), file("b.png"), file("c.pdf", "application/pdf")]);
    expect(batch.stage.value).toBe("choosing");
    expect(batch.items.value.map((item) => [item.place, item.chosen, item.pdf])).toEqual([
      [1, true, false],
      [2, true, false],
      [3, true, true],
    ]);
    expect(batch.items.value[2]!.thumb).toBeNull(); // a PDF has no picture
    batch.toggle(batch.items.value[1]!.id);
    expect(batch.chosen().map((item) => item.place)).toEqual([1, 3]);
    expect(deps.send).not.toHaveBeenCalled();
  });
});

describe("his one yes", () => {
  it("sends the chosen one at a time, in the order picked, and never the one left out", async () => {
    const { batch, deps, most } = rig(async (each) => {
      await new Promise((done) => setTimeout(done, 2));
      return card(each.name);
    });
    batch.pick([file("a.png"), file("b.png"), file("c.png")]);
    batch.toggle(batch.items.value[1]!.id);
    await batch.send();
    expect((deps.send as ReturnType<typeof vi.fn>).mock.calls.map(([each]) => (each as File).name)).toEqual(["a.png", "c.png"]);
    expect(most()).toBe(1);
    expect(batch.stage.value).toBe("done");
    expect(batch.items.value.map((item) => item.place)).toEqual([1, 3]);
  });

  it("leaves every paper with something said about it: a card, not a health paper, a refusal, or not sent", async () => {
    let online = false;
    const { batch, deps } = rig(async (each) => {
      if (each.name === "receipt.png") return card("receipt", false);
      if (each.name === "huge.png") throw new Refused("PhotoTooLarge", 413);
      if (each.name === "d.png" && !online) {
        online = true; // the network comes back before he taps Send the ones that did not go
        throw new Unreachable();
      }
      return card(each.name);
    });
    batch.pick([file("a.png"), file("receipt.png"), file("huge.png"), file("d.png"), file("e.png")]);
    await batch.send();
    expect(batch.items.value.map((item) => item.outcome.kind)).toEqual(["card", "notHealth", "refused", "notSent", "notSent"]);
    expect(deps.send).toHaveBeenCalledTimes(4); // e was not tried once the network had gone
    // Send the ones that did not go: only those two.
    (deps.send as ReturnType<typeof vi.fn>).mockClear();
    await batch.send();
    expect((deps.send as ReturnType<typeof vi.fn>).mock.calls.map(([each]) => (each as File).name)).toEqual(["d.png", "e.png"]);
  });

  it("marks a card checked once he has said yes to it", async () => {
    const { batch } = rig();
    batch.pick([file("a.png")]);
    await batch.send();
    batch.checked("a.png");
    expect(batch.items.value[0]!.outcome).toMatchObject({ kind: "card", checked: true });
  });
});

describe("nothing of a photo stays on the phone", () => {
  it("lets go of each picture and file as it is sent, keeps only what could not go, and lets go of everything on leaving", async () => {
    const { batch, deps } = rig(async (each) => {
      if (each.name === "d.png") throw new Unreachable();
      return card(each.name);
    });
    batch.pick([file("a.png"), file("b.png"), file("d.png")]);
    batch.toggle(batch.items.value[1]!.id);
    await batch.send();
    expect(deps.revoke).toHaveBeenCalledWith("blob:a.png");
    expect(deps.revoke).toHaveBeenCalledWith("blob:b.png"); // left out: let go at the yes
    expect(batch.holdsPhotos()).toBe(true); // d is still to be sent
    batch.forget();
    expect(deps.revoke).toHaveBeenCalledWith("blob:d.png");
    expect(batch.holdsPhotos()).toBe(false);
    expect(batch.items.value).toEqual([]);
  });

  it("has no browser storage anywhere in the code that holds the photos", () => {
    const dir = new URL("../../src/capture/", import.meta.url);
    const files = [
      ...readdirSync(dir).map((name) => new URL(name, dir)),
      new URL("../../src/screens/Papers.tsx", import.meta.url),
      new URL("../../src/screens/PaperBatch.tsx", import.meta.url),
    ];
    for (const path of files) expect(readFileSync(path, "utf8"), String(path)).not.toMatch(/localStorage|sessionStorage|indexedDB|kvSet|kvGet|caches\./);
  });
});

describe("a PDF", () => {
  it("is known by its type or its name, and goes the import way", () => {
    expect(isPdf({ type: "application/pdf", name: "x" })).toBe(true);
    expect(isPdf({ type: "", name: "LETTER.PDF" })).toBe(true);
    expect(isPdf({ type: "image/jpeg", name: "IMG_1.jpg" })).toBe(false);
  });
});

describe("the trace while a paper is sent", () => {
  it("shows every real step the backend gave, oldest first, done as the next one starts", async () => {
    const steps: [string, string][] = [
      ["stored", "Nura is keeping your paper safe."],
      ["reading", "Nura is looking at your paper."],
      ["found", "Nura found a blood test in your paper."],
    ];
    const seenAtEachStep: { key: string; text: string; done: boolean }[][] = [];
    const deps: BatchDeps = {
      thumb: () => null,
      revoke: vi.fn(),
      send: async (_each, onStep) => {
        for (const [key, text] of steps) {
          onStep(key, text);
          seenAtEachStep.push(batch.trace.value);
        }
        return card("a");
      },
      readable: () => true,
    };
    const batch = new PaperBatch(deps);
    batch.pick([file("a.png")]);
    await batch.send();
    // At the first step, one row, in progress. By the last, every earlier row is done.
    expect(seenAtEachStep[0]).toEqual([{ key: "stored", text: steps[0]![1], done: false }]);
    expect(seenAtEachStep[2]).toEqual([
      { key: "stored", text: steps[0]![1], done: true },
      { key: "reading", text: steps[1]![1], done: true },
      { key: "found", text: steps[2]![1], done: false },
    ]);
  });

  it("clears before the next paper in the batch, so one paper's steps never bleed into another's", async () => {
    const deps: BatchDeps = {
      thumb: () => null,
      revoke: vi.fn(),
      send: async (each, onStep) => {
        onStep("stored", `stored ${each.name}`);
        return card(each.name);
      },
      readable: () => true,
    };
    const batch = new PaperBatch(deps);
    batch.pick([file("a.png"), file("b.png")]);
    await batch.send();
    // Sending finished: nothing of the last paper's trace is left showing.
    expect(batch.trace.value).toEqual([]);
  });
});
