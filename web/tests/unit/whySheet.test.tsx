import { describe, expect, it, vi } from "vitest";
import { t } from "../../src/strings";
import { WhySheet, whySheetLines } from "../../src/screens/WhySheet";
import { item } from "./feedFixtures";
import { all, byTestId, one, render, text } from "./ui/render";

const s = t();

describe("whySheetLines", () => {
  it("reads the backend's own lines when it sent them", () => {
    const card = item("story", "story", { why: { kind: "story", plain: "This is why.", lines: ["Line one.", "Line two."] } });
    expect(whySheetLines(card)).toEqual(["Line one.", "Line two."]);
  });

  it("falls back to `plain` for a page the phone kept before this shipped", () => {
    const card = item("story", "story", { why: { kind: "story", plain: "This is why." } });
    expect(whySheetLines(card)).toEqual(["This is why."]);
  });

  it("is empty with no card open, and for a card with no reason at all", () => {
    expect(whySheetLines(null)).toEqual([]);
    expect(whySheetLines(item("story", "story", { why: { kind: "story" } }))).toEqual([]);
  });
});

describe("WhySheet", () => {
  it("is closed, and nothing rendered, with no card open", () => {
    expect(render(<WhySheet item={null} onClose={vi.fn()} s={s} />)).toEqual([]);
  });

  it("shows every line the backend sent, one per line, under its own Close", () => {
    const card = item("story", "story", {
      why: { kind: "story", plain: "This is why.", lines: ["You started amlodipine on 12 September.", "Because you wrote it down."] },
    });
    const close = vi.fn();
    const sheet = one(<WhySheet item={card} onClose={close} s={s} />);
    const [dialog] = all(sheet, (el) => el.props.role === "dialog");
    expect(dialog).toBeDefined();
    const lines = all(sheet, byTestId("why-sheet-line"));
    expect(lines.map((line) => text(line))).toEqual([
      "You started amlodipine on 12 September.",
      "Because you wrote it down.",
    ]);
    const [closeButton] = all(sheet, byTestId("sheet-close"));
    (closeButton!.props.onClick as () => void)();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("shows the withheld line as sent, never the card's own words, when the backend withheld it", () => {
    const card = item("story", "story", {
      scope: "readings",
      why: { kind: "story", plain: "Your blood pressure today was 138 over 84.", lines: ["This rests on a part of your papers that is withheld."] },
    });
    const sheet = one(<WhySheet item={card} onClose={vi.fn()} s={s} />);
    const lines = all(sheet, byTestId("why-sheet-line"));
    expect(lines).toHaveLength(1);
    expect(text(lines[0]!)).not.toContain("138");
  });
});
