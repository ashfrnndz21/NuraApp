import { describe, expect, it } from "vitest";
import type { AuditOut } from "../../src/api/types";
import { daysFromAudit, proudNumber } from "../../src/today/proud";

const entry = (at: string, target = "dose_taken", outcome: AuditOut["outcome"] = "allowed", action: AuditOut["action"] = "write"): AuditOut => ({
  entry_id: "x",
  at,
  action,
  scope: "medicines",
  target,
  outcome,
  refused_because: null,
});

const day = (iso: string) => iso.slice(0, 10);

describe("the proud number", () => {
  it("counts days, not taps: two taps on one day are one day", () => {
    expect(proudNumber(["2026-09-14", "2026-09-14", "2026-09-13"])).toBe(2);
  });

  it("is not a streak: a day with no tap takes nothing away", () => {
    expect(proudNumber(["2026-09-01", "2026-09-03", "2026-09-10"])).toBe(3);
  });

  it("only ever goes up: the floor the phone has shown holds", () => {
    const shown = proudNumber(["2026-09-01", "2026-09-02", "2026-09-03"]);
    expect(proudNumber(["2026-09-03"], shown)).toBe(3);
    expect(proudNumber([], shown)).toBe(3);
    expect(proudNumber(["2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"], shown)).toBe(4);
  });

  it("is monotonic under any sequence of observations", () => {
    let floor = 0;
    let last = 0;
    const observations = [["a"], [], ["a", "b"], ["c"], [], ["a", "b", "c", "d"], ["d"]];
    for (const seen of observations) {
      const next = proudNumber(seen, floor);
      expect(next).toBeGreaterThanOrEqual(last);
      last = next;
      floor = next;
    }
    expect(last).toBe(4);
  });

  it("reads only the Taken writes that landed from the trail", () => {
    const trail = [
      entry("2026-09-14T00:10:00Z"),
      entry("2026-09-14T12:00:00Z"),
      entry("2026-09-13T08:00:00Z"),
      entry("2026-09-12T08:00:00Z", "medication_line"),
      entry("2026-09-11T08:00:00Z", "dose_taken", "refused"),
      entry("2026-09-10T08:00:00Z", "dose_taken", "allowed", "read"),
    ];
    expect(daysFromAudit(trail, day).sort()).toEqual(["2026-09-13", "2026-09-14", "2026-09-14"]);
    expect(proudNumber(daysFromAudit(trail, day))).toBe(2);
  });
});
