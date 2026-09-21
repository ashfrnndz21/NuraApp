import { describe, expect, it } from "vitest";
import { ConnectionRow, Flag, Glass, Orb, RangeBar, Reveal, RevealGroup, SoftText, StatusLine } from "../../../src/ui/kit";
import { all, byType, hasClass, one, text } from "./render";

/** The dusk-glass conversational kit (P1 of the redesign, docs/design/experience-blueprint.html).
 *  Every component here is deliberately hookless (like `web/src/ui/kit/Conversation.tsx`), so
 *  these tests use the same lightweight, no-DOM harness as the rest of `ui/kit` (`./render`).
 *  `ActionSheet` and `ThreeStateButton` genuinely need a hook (a focus trap, an async action) and
 *  are tested separately, with a real DOM, in `actionSheet.test.tsx`. */

describe("Orb", () => {
  it("is decorative, and turns faster while Nura is really thinking", () => {
    const sm = one(<Orb testId="orb" />);
    expect(sm.props["aria-hidden"]).toBe("true");
    expect(hasClass("orb")(sm)).toBe(true);
    expect(hasClass("lg")(sm)).toBe(false);
    expect(hasClass("thinking")(sm)).toBe(false);
    const lg = one(<Orb size="lg" thinking testId="orb" />);
    expect(hasClass("lg")(lg)).toBe(true);
    expect(hasClass("thinking")(lg)).toBe(true);
  });
});

describe("StatusLine", () => {
  it("is ONE line, in a stable aria-live=polite region", () => {
    const el = one(<StatusLine text="Reading your medicines" testId="status" />);
    expect(el.props["aria-live"]).toBe("polite");
    expect(text(el)).toBe("Reading your medicines");
    // Exactly one status-line span inside the live region — never a stack of lines.
    expect(all(el, hasClass("status-line")).length).toBe(1);
  });

  it("carries a caller's own class alongside its own (ThinkingIndicator's thinking-line)", () => {
    const el = one(<StatusLine text="Nura is looking" className="thinking-line" />);
    const line = all(el, hasClass("status-line"))[0]!;
    expect(hasClass("thinking-line")(line)).toBe(true);
  });
});

describe("SoftText", () => {
  it("puts the full text in one visually-hidden reading, every word aria-hidden, *word* as the italic accent", () => {
    const el = one(<SoftText text="Your health, in *plain* words." testId="headline" />);
    // A real sr-only text node, not `aria-label` (axe's aria-prohibited-attr refuses that on a
    // plain paragraph/heading role).
    expect(text(all(el, hasClass("sr-only")))).toBe("Your health, in plain words.");
    const words = all(el, hasClass("soft-word"));
    expect(words.length).toBe(5);
    for (const w of words) expect(w.props["aria-hidden"]).toBe("true");
    const accent = all(el, hasClass("accent"))[0]!;
    expect(text(accent)).toBe("plain");
  });

  it("animates in every word on mount, when there is no previous text", () => {
    const el = one(<SoftText text="Show me your papers." />);
    const entering = all(el, hasClass("soft-word-enter"));
    expect(entering.length).toBe(4);
    // Staggered 62ms apart by default (the headline pace).
    expect(entering.map((w) => w.props.style)).toEqual([{ animationDelay: "0ms" }, { animationDelay: "62ms" }, { animationDelay: "124ms" }, { animationDelay: "186ms" }]);
  });

  it("animates only the words new since the last render, never replaying an old one", () => {
    const el = one(<SoftText text="Show me your papers today." previousText="Show me your papers" />);
    const words = all(el, hasClass("soft-word"));
    expect(words.length).toBe(5);
    // The four already-shown words carry no entrance class or delay at all.
    for (const w of words.slice(0, 4)) {
      expect(hasClass("soft-word-enter")(w)).toBe(false);
      expect(w.props.style).toBeUndefined();
    }
    // Only "today." is new, and it starts its own stagger from zero.
    expect(hasClass("soft-word-enter")(words[4]!)).toBe(true);
    expect(words[4]!.props.style).toEqual({ animationDelay: "0ms" });
  });

  it("uses the body pace (36ms) when asked, instead of the headline's 62ms", () => {
    const el = one(<SoftText text="one two three" pace="body" />);
    const words = all(el, hasClass("soft-word-enter"));
    expect(words.map((w) => w.props.style)).toEqual([{ animationDelay: "0ms" }, { animationDelay: "36ms" }, { animationDelay: "72ms" }]);
  });
});

describe("Reveal / RevealGroup", () => {
  it("Reveal is one reveal-item, ready for its @starting-style entrance", () => {
    const el = one(
      <Reveal testId="reveal">
        <p>Hello</p>
      </Reveal>,
    );
    expect(hasClass("reveal-item")(el)).toBe(true);
    expect(text(el)).toBe("Hello");
  });

  it("RevealGroup staggers each child's own transition-delay, 140ms apart by default", () => {
    const el = one(
      <RevealGroup testId="group">
        {[<p key="a">A</p>, <p key="b">B</p>, <p key="c">C</p>]}
      </RevealGroup>,
    );
    const items = all(el, hasClass("reveal-item"));
    expect(items.map((i) => i.props.style)).toEqual([{ transitionDelay: "0ms" }, { transitionDelay: "140ms" }, { transitionDelay: "280ms" }]);
  });

  it("RevealGroup honours a caller's own gap, within the 110-260ms band", () => {
    const el = one(
      <RevealGroup gap={200} testId="group">
        {[<p key="a">A</p>, <p key="b">B</p>]}
      </RevealGroup>,
    );
    const items = all(el, hasClass("reveal-item"));
    expect(items.map((i) => i.props.style)).toEqual([{ transitionDelay: "0ms" }, { transitionDelay: "200ms" }]);
  });
});

describe("Glass", () => {
  it("is a card (26px radius) or a row (18px), never both, with the shared glass fill", () => {
    const card = one(
      <Glass testId="card">
        <p>x</p>
      </Glass>,
    );
    expect(hasClass("glass-surface")(card)).toBe(true);
    expect(hasClass("glass-card")(card)).toBe(true);
    const row = one(
      <Glass shape="row" testId="row">
        <p>x</p>
      </Glass>,
    );
    expect(hasClass("glass-row")(row)).toBe(true);
    expect(hasClass("glass-card")(row)).toBe(false);
  });
});

describe("RangeBar", () => {
  it("draws the in-range segment and the reading's own marker, amber or sage", () => {
    const outOfRange = one(<RangeBar bandStart={0} bandWidth={65} markerAt={76} tone="attention" label="6.1 mmol/L, below 5.2" testId="bar" />);
    expect(outOfRange.props["aria-label"]).toBe("6.1 mmol/L, below 5.2");
    const marker = all(outOfRange, hasClass("range-bar-marker"))[0]!;
    expect(hasClass("ok")(marker)).toBe(false);
    const inRange = one(<RangeBar bandStart={40} bandWidth={20} markerAt={44} tone="ok" label="1.1 mmol/L, above 1.0" />);
    expect(hasClass("ok")(all(inRange, hasClass("range-bar-marker"))[0]!)).toBe(true);
  });
});

describe("Flag", () => {
  it("is ok (sage), attention (amber) or an outlined question — the backend's own word", () => {
    expect(hasClass("attention")(one(<Flag state="attention">Above</Flag>))).toBe(true);
    expect(hasClass("question")(one(<Flag state="question">Ask your doctor</Flag>))).toBe(true);
    const ok = one(<Flag state="ok">In range</Flag>);
    expect(hasClass("attention")(ok)).toBe(false);
    expect(hasClass("question")(ok)).toBe(false);
    expect(text(ok)).toBe("In range");
  });
});

describe("ConnectionRow", () => {
  it("is a real button when it goes somewhere, plain glass otherwise", () => {
    const onClick = () => {};
    const clickable = one(<ConnectionRow name="Dr Tan" line="Cardiologist" onClick={onClick} testId="row" />);
    expect(clickable.type).toBe("button");
    expect(clickable.props["data-testid"]).toBe("row");
    const plain = one(<ConnectionRow name="Mei" line="Daughter" />);
    expect(plain.type).toBe("div");
    expect(text(all(plain, byType("b")))).toBe("Mei");
    expect(text(all(plain, byType("small")))).toBe("Daughter");
  });
});
