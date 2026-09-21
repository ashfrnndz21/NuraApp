// @vitest-environment happy-dom
import { render as preactRender } from "preact";
import type { ComponentChild } from "preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionSheet, ThreeStateButton } from "../../../src/ui/kit";

/** `ActionSheet` and `ThreeStateButton` are the two kit components in this pass that genuinely
 *  need a hook — a real focus trap, a real async action — rather than the "no hook" display
 *  primitives the rest of `ui/kit` is (docs/design/motion.md, `web/src/ui/kit/Conversation.tsx`).
 *  That real interactivity cannot be exercised by the lightweight, no-DOM harness the rest of
 *  `ui/kit` tests with (`./render`, which calls a component as a plain function and cannot run a
 *  `useEffect` or dispatch a real keyboard event), so these run in a real DOM (happy-dom) with
 *  Preact's own `render`. */

function flush(): Promise<void> {
  // Preact schedules `useEffect` callbacks as a microtask after commit; a resolved promise tick
  // is enough to let them run before the next assertion.
  return new Promise((resolve) => setTimeout(resolve, 0));
}

let root: HTMLDivElement;

function mount(node: ComponentChild): void {
  root = document.createElement("div");
  document.body.appendChild(root);
  preactRender(node, root);
}

afterEach(() => {
  if (root) {
    preactRender(null, root);
    root.remove();
  }
});

describe("ActionSheet", () => {
  it("opens over the shell, with a title, a sub-line and a body slot", async () => {
    mount(
      <ActionSheet open title="Tell me in your own words" sub="Nura listens, then shows you what it wrote down" notNowLabel="Not now" onClose={() => {}} testId="sheet">
        <p>I have high blood pressure.</p>
      </ActionSheet>,
    );
    await flush();
    expect(root.querySelector('[data-testid="sheet"]')).toBeTruthy();
    expect(root.querySelector(".action-sheet-title")?.textContent).toBe("Tell me in your own words");
    expect(root.querySelector(".action-sheet-sub")?.textContent).toBe("Nura listens, then shows you what it wrote down");
    expect(root.querySelector(".action-sheet-body")?.textContent).toBe("I have high blood pressure.");
    expect(root.querySelector(".action-sheet-grab")).toBeTruthy();
    expect(root.querySelector('[data-testid="action-sheet-not-now"]')?.textContent).toBe("Not now");
  });

  it("renders nothing at all when closed", () => {
    mount(<ActionSheet open={false} title="x" notNowLabel="Not now" onClose={() => {}} testId="sheet" />);
    expect(root.querySelector('[data-testid="sheet"]')).toBeNull();
  });

  it("moves focus into the sheet on open, and traps Tab inside it", async () => {
    const opener = document.createElement("button");
    opener.textContent = "open";
    document.body.appendChild(opener);
    opener.focus();
    expect(document.activeElement).toBe(opener);

    mount(
      <ActionSheet
        open
        title="Add a paper"
        notNowLabel="Not now"
        onClose={() => {}}
        cta={{ label: "Save", busyLabel: "Saving…", doneLabel: "Saved", onAct: () => Promise.resolve() }}
        testId="sheet"
      />,
    );
    await flush();
    const panel = root.querySelector('[role="dialog"]') as HTMLElement;
    expect(document.activeElement).toBe(panel);

    const notNow = root.querySelector('[data-testid="action-sheet-not-now"]') as HTMLButtonElement;
    const cta = root.querySelector('[data-testid="action-sheet-cta"]') as HTMLButtonElement;
    // Shift+Tab from the first focusable (Not now) wraps to the last (the CTA).
    notNow.focus();
    let event = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(document.activeElement).toBe(cta);
    // Tab from the last wraps back to the first.
    event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(document.activeElement).toBe(notNow);

    opener.remove();
  });

  it("Escape closes it, and closing returns focus to whatever opened it", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const onClose = vi.fn();
    mount(<ActionSheet open title="x" notNowLabel="Not now" onClose={onClose} testId="sheet" />);
    await flush();
    expect(document.activeElement).not.toBe(opener);

    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(onClose).toHaveBeenCalledOnce();

    // The caller reacts to onClose by setting open=false; simulate that and confirm focus returns.
    mount(<ActionSheet open={false} title="x" notNowLabel="Not now" onClose={onClose} testId="sheet" />);
    await flush();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("a tap on the scrim closes it too, like 'Not now'", async () => {
    const onClose = vi.fn();
    mount(<ActionSheet open title="x" notNowLabel="Not now" onClose={onClose} testId="sheet" />);
    await flush();
    (root.querySelector(".action-sheet-scrim") as HTMLElement).click();
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("ThreeStateButton", () => {
  it("goes label -> busy -> done, exactly as long as the real action takes", async () => {
    let resolveAct: () => void = () => {};
    const onAct = vi.fn(() => new Promise<void>((resolve) => (resolveAct = resolve)));
    mount(<ThreeStateButton label="Save" busyLabel="Saving…" doneLabel="Saved" onAct={onAct} testId="cta" />);
    const button = root.querySelector('[data-testid="cta"]') as HTMLButtonElement;
    expect(button.textContent).toBe("Save");
    expect(button.disabled).toBe(false);

    button.click();
    await flush();
    expect(onAct).toHaveBeenCalledOnce();
    expect(button.textContent).toBe("Saving…");
    expect(button.disabled).toBe(true);

    resolveAct();
    await flush();
    expect(button.textContent).toContain("Saved");
    expect(button.disabled).toBe(true);
    expect(button.querySelector("svg")).toBeTruthy();
  });

  it("a second tap while busy or done does nothing — the action runs once", async () => {
    const onAct = vi.fn(() => Promise.resolve());
    mount(<ThreeStateButton label="Save" busyLabel="Saving…" doneLabel="Saved" onAct={onAct} testId="cta" />);
    const button = root.querySelector('[data-testid="cta"]') as HTMLButtonElement;
    button.click();
    button.click();
    await flush();
    button.click();
    await flush();
    expect(onAct).toHaveBeenCalledOnce();
  });

  it("a rejected action returns to idle, rather than pretending to have finished", async () => {
    const onAct = vi.fn(() => Promise.reject(new Error("offline")));
    mount(<ThreeStateButton label="Save" busyLabel="Saving…" doneLabel="Saved" onAct={onAct} testId="cta" />);
    const button = root.querySelector('[data-testid="cta"]') as HTMLButtonElement;
    button.click();
    await flush();
    await flush();
    expect(button.textContent).toBe("Save");
    expect(button.disabled).toBe(false);
  });
});
