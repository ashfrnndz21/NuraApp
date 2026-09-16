import { describe, expect, it, vi } from "vitest";
import {
  AskBar,
  Avatar,
  BrandMark,
  Chip,
  ChipRow,
  Dot,
  FeedCard,
  GlassTile,
  Hero,
  Icon,
  ICONS,
  initial,
  MemoCard,
  PanelList,
  PaperTile,
  PillButton,
  PlayerStrip,
  Poster,
  ProvenanceLine,
  ReviewField,
  SectionLabel,
  Sheet,
  Sparkline,
  sparkGeometry,
  TabBar,
  toneOf,
  WhyLine,
} from "../../../src/ui/kit";
import { all, byTestId, byType, hasClass, one, render, text } from "./render";

describe("Hero", () => {
  it("sits on the wash with no tile: a label, one big figure, one line", () => {
    const hero = one(<Hero greeting="Good morning, Pa." label="Most likely state" figure={2} words="medicines with breakfast" testId="hero" />);
    expect(hero.type).toBe("header");
    expect(hasClass("tile")(hero)).toBe(false);
    expect(text(all(hero, hasClass("hero-figure")))).toBe("2");
    expect(text(all(hero, hasClass("hero-words")))).toBe("medicines with breakfast");
    expect(text(all(hero, hasClass("hero-label")))).toBe("Most likely state");
  });

  it("draws no figure when the backend gave none — never a zero he did not earn", () => {
    expect(all(one(<Hero greeting="Good morning, Pa." figure={null} />), hasClass("hero-figure"))).toEqual([]);
    expect(all(one(<Hero figure={0} />), hasClass("hero-figure")).length).toBe(1);
  });
});

describe("PaperTile and GlassTile", () => {
  it("are the two surfaces, in one silhouette", () => {
    const paper = one(<PaperTile testId="p">A dose</PaperTile>);
    const glass = one(<GlassTile testId="g">A note</GlassTile>);
    expect(paper.props.class).toBe("tile paper");
    expect(glass.props.class).toBe("tile glass");
    expect(one(<PaperTile extra="settled">x</PaperTile>).props.class).toBe("tile paper settled");
  });

  it("label a section in sentence case on the wash", () => {
    const label = one(<SectionLabel>For you today</SectionLabel>);
    expect(label.type).toBe("h2");
    expect(label.props.class).toBe("section-label");
  });
});

describe("Chip", () => {
  it("is glass with Ink words, and a tone only as a dot beside the word", () => {
    const chip = one(<Chip tone="watch">Blood pressure</Chip>);
    expect(chip.props.class).toBe("glass-chip");
    expect(text(chip)).toBe("Blood pressure");
    expect(all(chip, hasClass("tone-dot"))[0]!.props["data-tone"]).toBe("watch");
    expect(all(one(<Chip>Bring your blood pressure book</Chip>), hasClass("tone-dot"))).toEqual([]);
    expect(one(<ChipRow>{[]}</ChipRow>).props.class).toBe("chip-row");
  });

  it("reads a tone only from the three state words", () => {
    expect([toneOf("good"), toneOf("watch"), toneOf("act"), toneOf("red"), toneOf(null)]).toEqual(["good", "watch", "act", null, null]);
    expect(one(<Dot tone={null} />).props["data-tone"]).toBe("none");
  });
});

describe("PillButton", () => {
  it("has the primary Plum, the secondary Paper outline and the coral pill", () => {
    const click = vi.fn();
    const primary = one(<PillButton variant="primary" onClick={click}>Looks right</PillButton>);
    const secondary = one(<PillButton onClick={click}>Taken</PillButton>);
    const coral = one(<PillButton variant="coral" onClick={click} testId="not-well">I'm not feeling well</PillButton>);
    expect(primary.props.class).toBe("pill plum");
    expect(secondary.props.class).toBe("pill");
    expect(coral.props.class).toBe("pill coral");
    expect(coral.props["data-testid"]).toBe("not-well");
    expect(primary.type).toBe("button");
    expect(primary.props.type).toBe("button");
    (coral.props.onClick as () => void)();
    expect(click).toHaveBeenCalledOnce();
  });

  it("puts its icon beside its word, never alone", () => {
    const hear = one(<PillButton variant="quiet" compact icon="speaker" onClick={() => undefined}>Hear</PillButton>);
    expect(hear.props.class).toBe("pill quiet compact");
    const [svg] = all(hear, byType("svg"));
    expect(svg!.props["aria-hidden"]).toBe("true");
    expect(text(hear)).toBe("Hear");
  });
});

describe("TabBar", () => {
  const tabs = [
    { id: "today", label: "Today", icon: "today" as const },
    { id: "medicines", label: "Medicines", icon: "medicines" as const },
    { id: "records", label: "Records", icon: "records" as const },
    { id: "visits", label: "Visits", icon: "visits" as const },
  ];

  it("is glass navigation with every icon beside its word, and says which tab is open", () => {
    const onSelect = vi.fn();
    const bar = one(<TabBar tabs={tabs} current="today" onSelect={onSelect} label="Nura" />);
    expect(bar.type).toBe("nav");
    expect(bar.props.class).toBe("tabbar");
    expect(bar.props["data-count"]).toBe(4);
    const buttons = all(bar, byType("button"));
    expect(buttons.map((button) => text(button))).toEqual(["Today", "Medicines", "Records", "Visits"]);
    for (const button of buttons) expect(all(button, byType("svg")).length).toBe(1);
    expect(buttons.map((button) => button.props["aria-current"])).toEqual(["page", undefined, undefined, undefined]);
    (buttons[2]!.props.onClick as () => void)();
    expect(onSelect).toHaveBeenCalledWith("records");
    expect(buttons[3]!.props["data-testid"]).toBe("tab-visits");
  });
});

describe("AskBar", () => {
  const base = { placeholder: "Ask Nura a question", label: "Your question", voiceLabel: "Speak", submitLabel: "Ask", onInput: () => undefined, onSubmit: () => undefined };

  it("offers the voice button while the field is empty, and Ask once there are words", () => {
    const voice = vi.fn();
    const empty = render(<AskBar {...base} value="" onVoice={voice} />);
    expect(all(empty, byTestId("ask-voice")).length).toBe(1);
    expect(all(empty, byTestId("ask-go")).length).toBe(0);
    (all(empty, byTestId("ask-voice"))[0]!.props.onClick as () => void)();
    expect(voice).toHaveBeenCalledOnce();
    const typed = render(<AskBar {...base} value="When is my next visit?" onVoice={voice} />);
    expect(all(typed, byTestId("ask-go")).length).toBe(1);
    expect(all(typed, byTestId("ask-voice")).length).toBe(0);
  });

  it("is a search form whose field has a name and the placeholder", () => {
    const bar = render(<AskBar {...base} value="" />);
    const [form] = all(bar, byType("form"));
    expect(form!.props.role).toBe("search");
    const [input] = all(bar, byType("input"));
    expect(input!.props.placeholder).toBe("Ask Nura a question");
    expect(text(all(bar, hasClass("sr-only")))).toBe("Your question");
    // Typing only: no voice button when the screen gives none.
    expect(all(bar, byTestId("ask-voice")).length).toBe(0);
  });

  it("asks on Enter only when there are words", () => {
    const submit = vi.fn();
    const preventDefault = vi.fn();
    const [form] = all(render(<AskBar {...base} value="  " onSubmit={submit} />), byType("form"));
    (form!.props.onSubmit as (event: unknown) => void)({ preventDefault });
    expect(submit).not.toHaveBeenCalled();
    const [again] = all(render(<AskBar {...base} value="Pills?" onSubmit={submit} />), byType("form"));
    (again!.props.onSubmit as (event: unknown) => void)({ preventDefault });
    expect(submit).toHaveBeenCalledOnce();
    expect(preventDefault).toHaveBeenCalledTimes(2);
  });
});

describe("Sparkline", () => {
  it("is one vertex per value, the last point marked, and the range band when there is one", () => {
    const shape = sparkGeometry([146, 142, 138], { width: 320, height: 64, band: { low: 120, high: 140 } })!;
    expect(shape.points.length).toBe(3);
    expect(shape.path.startsWith("M")).toBe(true);
    expect(shape.path.split("L").length).toBe(3);
    expect(shape.last).toEqual(shape.points[2]);
    expect(shape.points[0]!.y).toBeLessThan(shape.points[2]!.y); // higher value, higher on the page
    expect(shape.band!.height).toBeGreaterThan(0);
    expect(sparkGeometry([], { width: 320, height: 64 })).toBeNull();
    expect(sparkGeometry([138], { width: 320, height: 64 })!.path).toBe("");
  });

  it("draws a 1.5px Ink line, a band at 8% Plum, the marked last point — and no axes", () => {
    const figure = one(<Sparkline values={[146, 142, 138]} label="Blood pressure, the top number" band={{ low: 120, high: 140 }} tone="watch" />);
    const [svg] = all(figure, byType("svg"));
    expect(svg!.props.role).toBe("img");
    expect(svg!.props["aria-label"]).toBe("Blood pressure, the top number");
    expect(all(figure, hasClass("spark-line")).length).toBe(1);
    expect(all(figure, hasClass("spark-band")).length).toBe(1);
    expect(all(figure, hasClass("spark-last"))[0]!.props["data-tone"]).toBe("watch");
    expect(all(figure, (el) => ["line", "text", "g"].includes(el.type))).toEqual([]);
  });

  it("states the direction in words when it is given one, and draws nothing with no values", () => {
    const figure = one(<Sparkline values={[5.2, 5.6]} label="Sugar" caption="Sugar is better than March." />);
    expect(text(all(figure, byType("figcaption")))).toBe("Sugar is better than March.");
    expect(render(<Sparkline values={[]} label="Sugar" />)).toEqual([]);
  });
});

describe("ProvenanceLine and WhyLine", () => {
  it("are caption lines, and nothing when there is nothing to say", () => {
    expect(one(<ProvenanceLine>From the pharmacy label, 1 September.</ProvenanceLine>).props.class).toBe("source-line");
    const why = one(<WhyLine text="You are seeing this because a new test came in." />);
    expect(why.props.class).toBe("why-line");
    expect(why.props["data-testid"]).toBe("why");
    expect(render(<WhyLine text="" />)).toEqual([]);
    expect(render(<ProvenanceLine>{""}</ProvenanceLine>)).toEqual([]);
  });
});

describe("MemoCard", () => {
  it("is paper with the person's own words in quotes, the day it was filed and its visit", () => {
    const memo = one(<MemoCard quote={["Bring the book on Thursday.", "Lighter dinners."]} filed="Filed on Monday 14 September." attached="For your visit with Dr Tan." />);
    expect(memo.props.class).toBe("tile paper memo");
    expect(all(memo, byType("q")).map((q) => text(q))).toEqual(["Bring the book on Thursday.", "Lighter dinners."]);
    expect(all(memo, hasClass("source-line")).map((line) => text(line))).toEqual(["Filed on Monday 14 September.", "For your visit with Dr Tan."]);
  });
});

describe("PlayerStrip and Poster", () => {
  it("styles the player it is given and never plays by itself", () => {
    const strip = one(<PlayerStrip playing>{"the player"}</PlayerStrip>);
    expect(strip.props.class).toBe("player-strip");
    expect(strip.props["data-playing"]).toBe("true");
  });

  it("makes the whole poster the play button, with its word beside the mark", () => {
    const play = vi.fn();
    const poster = one(<Poster label="Play, 20 seconds" onPlay={play} wide />);
    expect(poster.type).toBe("button");
    expect(poster.props.class).toBe("poster wide");
    expect(text(poster)).toBe("Play, 20 seconds");
    (poster.props.onClick as () => void)();
    expect(play).toHaveBeenCalledOnce();
  });
});

describe("ReviewField", () => {
  it("underlines a sure value solid and one to check dotted", () => {
    const sure = one(<ReviewField label="Kidney number" value="98" sure />);
    const check = one(<ReviewField label="Potassium, a body salt" value="4.9" unit="mmol/L" sure={false} />);
    expect(all(sure, hasClass("review-value"))[0]!.props.class).toBe("review-value sure");
    expect(all(check, hasClass("review-value"))[0]!.props.class).toBe("review-value check");
    expect(check.props["data-sure"]).toBe("false");
    expect(text(check)).toContain("mmol/L");
  });
});

describe("Avatar and the brand mark", () => {
  it("shows the first letter of a name, whole, whatever the script", () => {
    expect(initial("mei")).toBe("M");
    expect(initial("  Ash ")).toBe("A");
    expect(initial("陈伟明")).toBe("陈");
    expect(initial("")).toBe("");
    const avatar = one(<Avatar name="Pa" soft />);
    expect(avatar.props.class).toBe("avatar soft");
    expect(avatar.props["aria-hidden"]).toBe("true");
  });

  it("draws the mark as it is: two strokes, the aura, the dot", () => {
    const mark = one(<BrandMark />);
    expect(mark.props["aria-hidden"]).toBe("true");
    expect(all(mark, byType("path")).length).toBe(2);
    expect(all(mark, byType("circle")).length).toBe(1);
    expect(all(mark, byType("path"))[0]!.props.stroke).toBe("#4E3A78");
  });
});

describe("Icon", () => {
  it("is a thin line the screen reader skips, for every icon there is", () => {
    for (const name of Object.keys(ICONS) as (keyof typeof ICONS)[]) {
      const svg = one(<Icon name={name} />);
      expect(svg.props.class).toBe("icon");
      expect(svg.props["aria-hidden"]).toBe("true");
      expect(svg.props.viewBox).toBe("0 0 24 24");
      expect(all(svg, byType("path")).length).toBeGreaterThan(0);
    }
  });
});

describe("PanelList", () => {
  it("is a titled list of the backend's lines, a dot only where a row has a tone", () => {
    const panel = one(
      <PanelList
        title="What changed"
        rows={[
          { text: "A kidney test came from Gleneagles.", tone: "watch" },
          { text: "Mei wrote about the walk.", tone: "good" },
          { text: "A visit was booked.", tone: null },
        ]}
        testId="what-changed"
      />,
    );
    expect(panel.props.class).toBe("tile glass panel");
    expect(all(panel, byType("li")).map((li) => text(li))).toEqual(["A kidney test came from Gleneagles.", "Mei wrote about the walk.", "A visit was booked."]);
    expect(all(panel, hasClass("tone-dot")).map((dot) => dot.props["data-tone"])).toEqual(["watch", "good", "none"]);
    const plain = one(<PanelList title="Watching for Pa" rows={[{ text: "Dengue in Air Itam", meta: "daily" }]} paper />);
    expect(plain.props.class).toBe("tile paper panel");
    expect(all(plain, hasClass("tone-dot"))).toEqual([]);
    expect(text(all(plain, hasClass("panel-meta")))).toBe("daily");
  });
});

describe("FeedCard", () => {
  it("is the card grammar: one number with its colour, the lines, the source, one action, why, and the spoken twin", () => {
    const card = one(
      <FeedCard
        title="Your sugar"
        figure="5.6"
        tone="good"
        direction="better than March"
        lines={["Sugar is better than March."]}
        boundary={["This is not a doctor's advice."]}
        source="From the clinic, 9 September."
        why="You are seeing this because a new test came in."
        action={<PillButton onClick={() => undefined}>Open</PillButton>}
        hear={<PillButton variant="quiet" compact icon="speaker" onClick={() => undefined}>Hear</PillButton>}
        testId="feed-card"
      />,
    );
    expect(card.props.class).toBe("tile paper card");
    expect(all(card, hasClass("card-figure"))[0]!.props["data-tone"]).toBe("good");
    expect(text(all(card, hasClass("number")))).toBe("5.6");
    expect(text(all(card, byTestId("boundary")))).toBe("This is not a doctor's advice.");
    const foot = all(card, hasClass("card-foot"))[0]!;
    expect(text(all(foot, hasClass("why-line")))).toBe("You are seeing this because a new test came in.");
    expect(text(all(foot, byType("button")))).toBe("Hear");
  });

  it("is glass when it carries no decision, and shows only what it was given", () => {
    const card = one(<FeedCard lines={["Pour out the water in the pots."]} paper={false} />);
    expect(card.props.class).toBe("tile glass card");
    expect(all(card, hasClass("card-foot"))).toEqual([]);
    expect(all(card, hasClass("card-figure"))).toEqual([]);
  });
});

describe("Sheet", () => {
  it("is a modal dialog with its own Close button, and nothing when closed", () => {
    const close = vi.fn();
    expect(render(<Sheet title="Me" open={false} onClose={close} closeLabel="Close">x</Sheet>)).toEqual([]);
    const layer = one(<Sheet title="Me" open onClose={close} closeLabel="Close" testId="me-sheet">{"inside"}</Sheet>);
    const [dialog] = all(layer, (el) => el.props.role === "dialog");
    expect(dialog!.props["aria-modal"]).toBe("true");
    expect(dialog!.props["aria-labelledby"]).toBe("sheet-title");
    const [closeButton] = all(layer, byTestId("sheet-close"));
    expect(text(closeButton!)).toBe("Close");
    (closeButton!.props.onClick as () => void)();
    (all(layer, hasClass("sheet-scrim"))[0]!.props.onClick as () => void)();
    expect(close).toHaveBeenCalledTimes(2);
  });
});
