import { describe, expect, it, vi } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { LanguageRow, ProfileHeader, ProfileNav, SignOutRow, signalLabel, signalLead } from "../../src/screens/ProfileParts";
import { stringsFor } from "../../src/strings";
import { all, byTestId, byType, hasClass, one, render, text } from "./ui/render";

const en = stringsFor("en");

const OWN: ProfileOut = {
  profile_id: "pa",
  display_name: "Pa",
  language: "en",
  region: "SG",
  role: null,
  scopes: [],
  standing: "owner",
  key_id: null,
};

const HIS: ProfileOut = { ...OWN, display_name: "Pa", standing: "steward", key_id: "key-1", scopes: ["records"] };

describe("the Profile tab's header (docs/design/nura-concept-board.html)", () => {
  it("names whoever is signed in — never whoever's papers happen to be open elsewhere", () => {
    const header = one(<ProfileHeader s={en} name="Mei" />);
    expect(text(all(header, hasClass("list-title")))).toBe("Mei");
    expect(text(all(header, hasClass("list-line")))).toBe("You are signed in as Mei.");
  });
});

describe("the Profile tab's language picker", () => {
  it("shows his own three, one chosen, and sets on a tap", () => {
    const onSet = vi.fn();
    const names = { en: "English", ms: "Bahasa Melayu", zh: "中文" } as const;
    const rendered = render(<LanguageRow s={en} code="en" names={names} onSet={onSet} />);
    const pills = all(rendered, byType("button"));
    expect(pills.map((pill) => text(pill))).toEqual(["English", "Bahasa Melayu", "中文"]);
    expect(pills.find((pill) => pill.props["data-testid"] === "lang-en")!.props.class).toContain("chosen");
    expect(pills.find((pill) => pill.props["data-testid"] === "lang-ms")!.props.class).not.toContain("chosen");
    (pills.find((pill) => pill.props["data-testid"] === "lang-ms")!.props.onClick as () => void)();
    expect(onSet).toHaveBeenCalledWith("ms");
  });
});

describe("the Profile tab's list (docs/design/nura-concept-board.html, the Profile screen)", () => {
  it("on his own Profile: 'Change who can see what', what he agreed to as his own, sign out — every row wired", () => {
    const onOpenKeys = vi.fn();
    const onOpenConsents = vi.fn();
    const onOpenOnlyMe = vi.fn();
    const onOpenEmergency = vi.fn();
    const nav = one(
      <ProfileNav
        s={en}
        papers={OWN}
        owner
        showEmergency
        onOpenEmergency={onOpenEmergency}
        onOpenKeys={onOpenKeys}
        onOpenConsents={onOpenConsents}
        onOpenOnlyMe={onOpenOnlyMe}
        onSwitchProfile={() => undefined}
        onSetUp={null}
        onOpenPapers={null}
      />,
    );
    expect(text(all(nav, byTestId("profile-consents")))).toBe(en.family.consentsSelf);
    expect(text(all(nav, byTestId("profile-keys")))).toBe(en.family.keys);
    expect(text(all(nav, byTestId("profile-only-me")))).toBe(en.family.onlyMe);
    expect(text(all(nav, byTestId("me-emergency")))).toBe(en.today.emergencyTitle);
    (all(nav, byTestId("profile-keys"))[0]!.props.onClick as () => void)();
    expect(onOpenKeys).toHaveBeenCalledOnce();
    (all(nav, byTestId("profile-consents"))[0]!.props.onClick as () => void)();
    expect(onOpenConsents).toHaveBeenCalledOnce();
    (all(nav, byTestId("profile-only-me"))[0]!.props.onClick as () => void)();
    expect(onOpenOnlyMe).toHaveBeenCalledOnce();
    (all(nav, byTestId("me-emergency"))[0]!.props.onClick as () => void)();
    expect(onOpenEmergency).toHaveBeenCalledOnce();
  });

  it("on a chief's read of his papers: the same rows say his name instead of 'you' (the *Other twin), and no emergency row without the scope", () => {
    const nav = one(
      <ProfileNav
        s={en}
        papers={HIS}
        owner={false}
        showEmergency={false}
        onOpenEmergency={() => undefined}
        onOpenKeys={() => undefined}
        onOpenConsents={() => undefined}
        onOpenOnlyMe={() => undefined}
        onSwitchProfile={() => undefined}
        onSetUp={null}
        onOpenPapers={null}
      />,
    );
    expect(text(all(nav, byTestId("profile-consents")))).toBe("What Pa said yes to");
    expect(all(nav, byTestId("me-emergency"))).toEqual([]);
  });

  it("only offers Set up and Add papers from photos where they apply", () => {
    const onSetUp = vi.fn();
    const withBoth = one(
      <ProfileNav
        s={en}
        papers={OWN}
        owner
        showEmergency={false}
        onOpenEmergency={() => undefined}
        onOpenKeys={() => undefined}
        onOpenConsents={() => undefined}
        onOpenOnlyMe={() => undefined}
        onSwitchProfile={() => undefined}
        onSetUp={onSetUp}
        onOpenPapers={() => undefined}
      />,
    );
    expect(all(withBoth, byTestId("set-up")).length).toBe(1);
    expect(all(withBoth, byTestId("open-papers")).length).toBe(1);
    const withNeither = one(
      <ProfileNav
        s={en}
        papers={OWN}
        owner
        showEmergency={false}
        onOpenEmergency={() => undefined}
        onOpenKeys={() => undefined}
        onOpenConsents={() => undefined}
        onOpenOnlyMe={() => undefined}
        onSwitchProfile={() => undefined}
        onSetUp={null}
        onOpenPapers={null}
      />,
    );
    expect(all(withNeither, byTestId("set-up"))).toEqual([]);
    expect(all(withNeither, byTestId("open-papers"))).toEqual([]);
  });
});

describe("sign out, on its own row", () => {
  it("is a working row, not a decoration", () => {
    const onSignOut = vi.fn();
    const row = one(<SignOutRow s={en} onSignOut={onSignOut} />);
    const button = all(row, byTestId("sign-out"))[0]!;
    expect(text(button)).toBe(en.me.signOut);
    (button.props.onClick as () => void)();
    expect(onSignOut).toHaveBeenCalledOnce();
  });
});

describe("'What Nura uses' (RE-05), said as his own or by his name (the *_THEIRS twins)", () => {
  const families = ["food", "sleep", "steps", "water", "search_topics"] as const;

  it("reads as 'your' on his own Profile", () => {
    expect(signalLead(en, true, "Pa")).toBe(en.me.whatNuraUsesLead);
    for (const family of families) expect(signalLabel(en, true, family, "Pa")).toBe(en.me.whatNuraUsesFamilies[family]);
  });

  it("reads with his name on a chief's read of his papers", () => {
    expect(signalLead(en, false, "Pa")).toBe("Choose what Nura may use to suggest reads and videos for Pa.");
    expect(signalLabel(en, false, "food", "Pa")).toBe("What Pa eats");
    expect(signalLabel(en, false, "sleep", "Pa")).toBe("Pa's sleep");
  });

  it("has both twins in every language, for every family", () => {
    for (const code of ["en", "ms", "zh"] as const) {
      const s = stringsFor(code);
      expect(signalLead(s, true, "Pa")).toBeTruthy();
      expect(signalLead(s, false, "Pa")).toBeTruthy();
      for (const family of families) {
        expect(signalLabel(s, true, family, "Pa")).toBeTruthy();
        expect(signalLabel(s, false, family, "Pa")).toBeTruthy();
      }
    }
  });
});
