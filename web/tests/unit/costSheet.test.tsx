import { describe, expect, it, vi } from "vitest";
import type { CostExpectationOut } from "../../src/api/types";
import { t } from "../../src/strings";
import { CostSheet } from "../../src/screens/CostSheet";
import { all, byTestId, one, render, text } from "./ui/render";

const s = t();

function cost(overrides: Partial<CostExpectationOut> = {}): CostExpectationOut {
  return {
    appointment_id: "11111111-1111-1111-1111-111111111111",
    found: true,
    low_cents: 3800,
    high_cents: 21500,
    low_said: "S$38",
    high_said: "S$215",
    currency: "S$",
    source: { publisher: "Ministry of Health Singapore", url: "https://www.moh.gov.sg/fee-benchmarks", fetched_at: "2026-03-01" },
    covered_shown: true,
    covered_low_cents: 0,
    covered_high_cents: 21500,
    covered_low_said: "S$0",
    covered_high_said: "S$215",
    note: ["This is a typical range, not a quote.", "Ask what this visit will cost before he goes."],
    ...overrides,
  };
}

describe("CostSheet", () => {
  it("is closed, and nothing rendered, with cost not yet loaded", () => {
    expect(render(<CostSheet cost={null} open={false} onClose={vi.fn()} owner patientName="Pa" locale="en-SG" s={s} />)).toEqual([]);
  });

  it("shows the cited range, the source and every note line, under its own Close", () => {
    const close = vi.fn();
    const sheet = one(<CostSheet cost={cost()} open onClose={close} owner patientName="Pa" locale="en-SG" s={s} />);
    const [dialog] = all(sheet, (el) => el.props.role === "dialog");
    expect(dialog).toBeDefined();

    const [range] = all(sheet, byTestId("cost-range"));
    expect(text(range!)).toBe("S$38 – S$215");

    const [source] = all(sheet, byTestId("cost-source"));
    expect(text(source!)).toContain("Ministry of Health Singapore");

    const lines = all(sheet, byTestId("cost-note-line"));
    expect(lines.map((line) => text(line))).toEqual([
      "This is a typical range, not a quote.",
      "Ask what this visit will cost before he goes.",
    ]);

    const [closeButton] = all(sheet, byTestId("sheet-close"));
    (closeButton!.props.onClick as () => void)();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("shows the covered range labelled 'your cover may pay' for the owner's own view", () => {
    const sheet = one(<CostSheet cost={cost()} open onClose={vi.fn()} owner patientName="Pa" locale="en-SG" s={s} />);
    const [covered] = all(sheet, byTestId("cost-covered"));
    expect(text(covered!)).toContain("Your cover may pay");
    expect(text(covered!)).toContain("S$0 – S$215");
  });

  it("never shows a covered range or figure when the caller does not hold Scope.MONEY", () => {
    const withheld = cost({ covered_shown: false, covered_low_said: null, covered_high_said: null });
    const sheet = one(<CostSheet cost={withheld} open onClose={vi.fn()} owner patientName="Pa" locale="en-SG" s={s} />);
    expect(all(sheet, byTestId("cost-covered"))).toEqual([]);
  });

  it("shows only the honest note lines, no range and no source, when no benchmark was found", () => {
    const notFound = cost({
      found: false,
      low_cents: null,
      high_cents: null,
      low_said: null,
      high_said: null,
      source: null,
      covered_shown: false,
      covered_low_said: null,
      covered_high_said: null,
      note: ["Nura could not find a typical fee for this.", "Ask what this visit will cost before he goes."],
    });
    const sheet = one(<CostSheet cost={notFound} open onClose={vi.fn()} owner patientName="Pa" locale="en-SG" s={s} />);
    expect(all(sheet, byTestId("cost-range"))).toEqual([]);
    expect(all(sheet, byTestId("cost-source"))).toEqual([]);
    const lines = all(sheet, byTestId("cost-note-line"));
    expect(lines.map((line) => text(line))).toEqual([
      "Nura could not find a typical fee for this.",
      "Ask what this visit will cost before he goes.",
    ]);
  });
});
