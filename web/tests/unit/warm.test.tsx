import { describe, expect, it, vi } from "vitest";
import { recordTab, tabsFor } from "../../src/nav";
import { stringsFor } from "../../src/strings";
import { CheckInFace, CoupleIllustration, ParkIllustration, SeedlingIllustration, WelcomeIllustration } from "../../src/ui/illustrations";
import { Avatar, Exchange, FeatureTile, Hero, MetricRow, ProgressRing, SectionHeader, SkeletonCard, StatusPill, StepTrace, ThinkingIndicator } from "../../src/ui/kit";
import { byTestId } from "./ui/render";
import { all, byType, hasClass, one, render as renderAll, text } from "./ui/render";

const en = stringsFor("en");

describe("the five tabs (docs/design-direction.md)", () => {
  it("are Today, Health, Family, Visits and Me for the owner, in either density", () => {
    for (const density of ["patient", "caregiver"] as const) {
      expect(tabsFor(density, en).map((tab) => tab.label)).toEqual(["Today", "Health", "Family", "Visits", "Me"]);
    }
  });

  it("show a key only the tabs its scopes open, the same list in either density", () => {
    const medicinesOnly = tabsFor("caregiver", en, ["medicines"], false).map((tab) => tab.id);
    expect(medicinesOnly).toEqual(["home", "health", "profile"]);
    expect(tabsFor("patient", en, ["medicines"], false).map((tab) => tab.id)).toEqual(medicinesOnly);
    expect(tabsFor("caregiver", en, ["family", "visits"], false).map((tab) => tab.id)).toEqual(["home", "health", "connect", "services", "profile"]);
  });

  it("put every place in his papers under Health", () => {
    expect(recordTab({ name: "medicines" }, "patient")).toBe("health");
    expect(recordTab({ name: "papers" }, "caregiver")).toBe("health");
  });

  it("are named in all three languages", () => {
    for (const code of ["en", "ms", "zh"] as const) {
      const s = stringsFor(code);
      for (const key of ["home", "health", "connect", "services", "profile"] as const) expect(s.tabs[key]).toBeTruthy();
    }
  });
});

describe("the illustrations", () => {
  it("are decorative: hidden from the screen reader, never focusable", () => {
    for (const Picture of [CoupleIllustration, WelcomeIllustration, CheckInFace, SeedlingIllustration, ParkIllustration]) {
      const svg = one(<Picture />);
      expect(svg.type).toBe("svg");
      expect(svg.props["aria-hidden"]).toBe("true");
      expect(svg.props.focusable).toBe("false");
      expect(all(svg, byType("text"))).toEqual([]);
      // Every colour a token: no raw colour in a shape.
      for (const shape of all(svg, (el) => el.type !== "svg" && el.type !== "g")) {
        expect(shape.props.fill, "fill").toBeUndefined();
        expect(JSON.stringify(shape.props.style ?? {})).not.toMatch(/#[0-9a-f]{3,6}/i);
      }
    }
  });
});

describe("the warm components", () => {
  it("a feature tile is one button: its tint, an icon, its word and its caption", () => {
    const onClick = vi.fn();
    const tile = one(<FeatureTile icon="health" tint="blush" label="Health" caption="Papers and tests" onClick={onClick} testId="do-health" />);
    expect(tile.type).toBe("button");
    expect(tile.props["data-tint"]).toBe("blush");
    expect(text(tile)).toBe("HealthPapers and tests");
    expect(all(tile, byType("svg"))[0]!.props["aria-hidden"]).toBe("true");
    (tile.props.onClick as () => void)();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("the hero's wave and picture never enter the greeting's words", () => {
    const hero = one(<Hero greeting="Good morning, Pa." wave ask="How are you feeling today?" art={<CoupleIllustration />} />);
    expect(text(all(hero, hasClass("hero-greeting")))).toBe("Good morning, Pa.");
    expect(all(hero, hasClass("hero-wave"))[0]!.props["aria-hidden"]).toBe("true");
    expect(text(all(hero, hasClass("hero-ask")))).toBe("How are you feeling today?");
  });

  it("the ring shows a real count as text, the ring itself decorative", () => {
    const ring = one(<ProgressRing done={12} of={14} figure="12" label="doses taken this week" testId="ring" />);
    expect(all(ring, byType("svg"))[0]!.props["aria-hidden"]).toBe("true");
    expect(text(all(ring, hasClass("ring-number")))).toBe("12");
    expect(text(all(ring, hasClass("ring-label")))).toBe("doses taken this week");
  });

  it("a section header is a heading, and its See all names what it opens", () => {
    const head = one(<SectionHeader title="Coming up" action={{ word: "See all", label: "See all visits", onClick: () => undefined }} />);
    expect(text(all(head, byType("h2")))).toBe("Coming up");
    expect(all(head, byType("button"))[0]!.props["aria-label"]).toBe("See all visits");
  });

  it("an avatar is their own photo, else their initial — never a stock face", () => {
    expect(one(<Avatar name="Mei" photo="blob:mei" />).type).toBe("img");
    const initial = one(<Avatar name="Mei" tint="sage" />);
    expect(text(initial)).toBe("M");
    expect(initial.props["data-tint"]).toBe("sage");
  });

  it("a metric row and a status pill carry their words, not just a colour", () => {
    expect(text(one(<MetricRow icon="pulse" tint="sky" label="Blood pressure" value="138/84" />))).toBe("Blood pressure138/84");
    expect(text(one(<StatusPill tone="good">Good</StatusPill>))).toBe("Good");
  });
});

describe("conversation, waiting and thinking (docs/design-direction.md)", () => {
  const words = en.talk;
  const steps = [
    { key: "medicines", text: "Reading the medicines", done: true },
    { key: "visits", text: "Checking the visits", done: false },
  ];

  it("shows only the steps it is given, each in progress or done, under Nura is looking", () => {
    const trace = one(<StepTrace steps={steps} working={words.working} />);
    expect(text(all(trace, hasClass("thinking-line")))).toBe(words.working);
    expect(all(trace, byType("li")).map((li) => [text(li), li.props["data-done"]])).toEqual([
      ["Reading the medicines", "true"],
      ["Checking the visits", "false"],
    ]);
    expect(all(trace, hasClass("trace-tick")).length).toBe(1);
    expect(all(trace, hasClass("trace-spin")).length).toBe(1);
    expect(all(one(<StepTrace steps={[]} working={words.working} />), byType("li"))).toEqual([]);
  });

  it("folds the steps into What Nura looked at under the answer, with its sources and boundary", () => {
    const exchange = one(<Exchange question="Q" steps={steps} status="answered" answer="A" sources={["Medicines", "Visit, 2 Sep"]} boundary={["Nura does not decide what is wrong."]} lookedAt="What Nura looked at: medicines, visits" words={words} />);
    const answer = all(exchange, byTestId("exchange-answer"))[0]!;
    expect(all(answer, hasClass("source-chip")).map((chip) => text(chip))).toEqual(["Medicines", "Visit, 2 Sep"]);
    expect(text(all(answer, byTestId("answer-boundary")))).toBe("Nura does not decide what is wrong.");
    const looked = all(answer, byType("details"))[0]!;
    expect(text(all(looked, byType("summary")))).toBe("What Nura looked at: medicines, visits");
    expect(all(looked, byType("li")).length).toBe(2);
    expect(all(exchange, hasClass("thinking"))).toEqual([]);
  });

  it("shows an answer the moment it is given, even while the caller still says working", () => {
    const exchange = one(<Exchange question="When is my next visit?" steps={steps} status="working" answer={<p>Monday at half past 10.</p>} words={words} />);
    expect(exchange.props["data-status"]).toBe("answered");
    expect(all(exchange, byTestId("thinking"))).toEqual([]);
    expect(text(all(exchange, byTestId("exchange-answer")))).toContain("Monday at half past 10.");
  });

  it("announces the start and the answer through one polite region, never a step", () => {
    const working = one(<Exchange question="Q" steps={steps} status="working" words={words} />);
    const live = all(working, byTestId("exchange-live"));
    expect(live.length).toBe(1);
    expect(live[0]!.props["aria-live"]).toBe("polite");
    expect(text(live)).toBe(words.working);
    for (const li of all(working, byType("li"))) expect(li.props["aria-live"]).toBeUndefined();
    const answered = one(<Exchange question="Q" steps={steps} status="answered" answer="A" words={words} />);
    expect(text(all(answered, byTestId("exchange-live")))).toBe(words.answered);
  });

  it("never says it has answered when no answer was given", () => {
    const empty = one(<Exchange question="Q" steps={steps} status="answered" words={words} />);
    expect(empty.props["data-status"]).toBe("working");
    expect(text(all(empty, byTestId("exchange-live")))).toBe(words.working);
    expect(all(empty, byTestId("exchange-answer"))).toEqual([]);
  });

  it("says a long wait or a failure plainly and offers Try again", () => {
    const retry = vi.fn();
    const failed = one(<Exchange question="Q" steps={[]} status="failed" words={words} onRetry={retry} />);
    expect(text(all(failed, byTestId("exchange-failed")))).toContain(words.failed);
    (all(failed, byTestId("exchange-retry"))[0]!.props.onClick as () => void)();
    expect(retry).toHaveBeenCalledOnce();
    const slow = one(<Exchange question="Q" steps={[]} status="slow" words={words} onRetry={retry} />);
    expect(text(all(slow, byTestId("exchange-slow")))).toContain(words.slow);
    expect(all(slow, byTestId("exchange-retry")).length).toBe(1);
  });

  it("the thinking indicator's dots are decorative and give way to the brand mark's motion", () => {
    const dots = one(<ThinkingIndicator line={words.working} />);
    expect(all(dots, hasClass("thinking-mark"))[0]!.props["aria-hidden"]).toBe("true");
    expect(text(all(dots, hasClass("thinking-line")))).toBe(words.working);
    const marked = one(<ThinkingIndicator line={words.working} mark={<svg class="speaking" />} />);
    expect(all(marked, hasClass("thinking-dots"))).toEqual([]);
    expect(all(marked, hasClass("speaking")).length).toBe(1);
  });

  it("a skeleton is a hidden placeholder in the card's shape", () => {
    const card = one(<SkeletonCard shape="tile" lines={2} />);
    expect(card.props["aria-hidden"]).toBe("true");
    expect(card.props["data-shape"]).toBe("tile");
    expect(all(card, hasClass("skeleton-bar")).length).toBe(3);
  });

  it("has its words in all three languages", () => {
    for (const code of ["en", "ms", "zh"] as const) for (const line of Object.values(stringsFor(code).talk)) expect(line).toBeTruthy();
  });
});

function render0(node: unknown): unknown {
  const nodes = renderAll(node);
  return nodes.length === 0 ? null : nodes;
}
