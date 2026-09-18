import { describe, expect, it, vi } from "vitest";
import type { NavigationDraftOut } from "../../src/api/types";
import { NavigationDraftSheet } from "../../src/screens/NavigationDraftSheet";
import { stringsFor } from "../../src/strings";
import { all, byTestId, one, render, text } from "./ui/render";

const en = stringsFor("en");

function draft(overrides: Partial<NavigationDraftOut> = {}): NavigationDraftOut {
  return {
    need_id: "follow_up:1",
    kind: "follow_up",
    language: "en",
    text: "Pa is writing this.\nCould we book a check-up, please?",
    drafted_by: "self",
    links: [{ kind: "sms", href: "sms:+6598765432" }, { kind: "whatsapp", href: "https://wa.me/6598765432" }],
    copy_only: false,
    cites: ["fact:1"],
    ...overrides,
  };
}

describe("NavigationDraftSheet", () => {
  it("is closed, and nothing rendered, when nothing is being drafted", () => {
    expect(
      render(
        <NavigationDraftSheet
          s={en}
          open={false}
          draft={null}
          loading={false}
          error={false}
          text=""
          onTextChange={vi.fn()}
          copied={false}
          onCopy={vi.fn()}
          onClose={vi.fn()}
        />,
      ),
    ).toEqual([]);
  });

  it("shows the loading line while the draft has not come back yet", () => {
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={null}
        loading
        error={false}
        text=""
        onTextChange={vi.fn()}
        copied={false}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(text(all(sheet, byTestId("navigation-draft-loading")))).toBe("Nura is writing the message.");
    expect(all(sheet, byTestId("navigation-draft-text"))).toEqual([]);
  });

  it("shows the error line when the draft could not be written", () => {
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={null}
        loading={false}
        error
        text=""
        onTextChange={vi.fn()}
        copied={false}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(text(all(sheet, byTestId("navigation-draft-error")))).toBe("Nura could not write the message just now.");
  });

  it("shows the drafted text, editable, and a send link for each contact Nura built from the provider's own phone", () => {
    const onTextChange = vi.fn();
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft()}
        loading={false}
        error={false}
        text="Pa is writing this.\nCould we book a check-up, please?"
        onTextChange={onTextChange}
        copied={false}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const [field] = all(sheet, byTestId("navigation-draft-text"));
    expect(field).toBeDefined();
    expect(field!.props.value).toContain("Could we book a check-up, please?");

    const sms = all(sheet, byTestId("navigation-draft-link-sms"));
    expect(sms).toHaveLength(1);
    expect(sms[0]!.props.href).toBe("sms:+6598765432");
    const wa = all(sheet, byTestId("navigation-draft-link-whatsapp"));
    expect(wa).toHaveLength(1);
    expect(wa[0]!.props.href).toBe("https://wa.me/6598765432");

    expect(all(sheet, byTestId("navigation-draft-copy-only"))).toEqual([]);
  });

  it("never sends anything itself: there is no send action, only send links and Copy", () => {
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft()}
        loading={false}
        error={false}
        text="text"
        onTextChange={vi.fn()}
        copied={false}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const links = [...all(sheet, byTestId("navigation-draft-link-sms")), ...all(sheet, byTestId("navigation-draft-link-whatsapp"))];
    for (const link of links) expect(link.type).toBe("a"); // a link the person follows themselves, never a fetch Nura makes
  });

  it("Copy calls back, and shows Copied once it has", () => {
    const onCopy = vi.fn();
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft()}
        loading={false}
        error={false}
        text="text"
        onTextChange={vi.fn()}
        copied={false}
        onCopy={onCopy}
        onClose={vi.fn()}
      />,
    );
    const [copyButton] = all(sheet, byTestId("navigation-draft-copy"));
    (copyButton!.props.onClick as () => void)();
    expect(onCopy).toHaveBeenCalledOnce();
    expect(all(sheet, byTestId("navigation-draft-copied"))).toEqual([]);

    const copied = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft()}
        loading={false}
        error={false}
        text="text"
        onTextChange={vi.fn()}
        copied
        onCopy={onCopy}
        onClose={vi.fn()}
      />,
    );
    expect(text(all(copied, byTestId("navigation-draft-copied")))).toBe("It is copied, ready to paste where you send it.");
  });

  it("says plainly when there is no number on file: no links, and the copy-only line", () => {
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft({ links: [], copy_only: true })}
        loading={false}
        error={false}
        text="text"
        onTextChange={vi.fn()}
        copied={false}
        onCopy={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(all(sheet, byTestId("navigation-draft-link-sms"))).toEqual([]);
    expect(all(sheet, byTestId("navigation-draft-link-whatsapp"))).toEqual([]);
    expect(text(all(sheet, byTestId("navigation-draft-copy-only")))).toBe(
      "There is no number for this place, so copy the message and send it yourself.",
    );
  });

  it("Close calls back", () => {
    const onClose = vi.fn();
    const sheet = one(
      <NavigationDraftSheet
        s={en}
        open
        draft={draft()}
        loading={false}
        error={false}
        text="text"
        onTextChange={vi.fn()}
        copied={false}
        onCopy={vi.fn()}
        onClose={onClose}
      />,
    );
    const [closeButton] = all(sheet, byTestId("sheet-close"));
    (closeButton!.props.onClick as () => void)();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
