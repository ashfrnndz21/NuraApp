import { describe, expect, it } from "vitest";
import { installRestoreGuard } from "../../src/restoreGuard";

/** #142: a tap that starts while the restore check (`afterSignIn`, W1) is still on — nothing
 *  painted yet, on purpose, for a shared phone — must never resolve into whatever the screen
 *  becomes once the restore lands, however quickly that happens to be. */
describe("the restore guard (#142)", () => {
  it("swallows the click a gesture produces when its pointerdown began during the restore, before anything else sees it", () => {
    const target = new EventTarget();
    let restoring = true;
    installRestoreGuard(target, () => restoring);
    let sawClick = false;
    target.addEventListener("click", () => {
      sawClick = true;
    });

    target.dispatchEvent(new Event("pointerdown"));
    // The restore lands mid-gesture: Today fills the screen under the still-down finger.
    restoring = false;
    const click = new Event("click", { cancelable: true });
    target.dispatchEvent(click);

    expect(sawClick).toBe(false);
    expect(click.defaultPrevented).toBe(true);
  });

  it("leaves a tap alone once the restore is already over when the gesture starts — no delay to wait out", () => {
    const target = new EventTarget();
    installRestoreGuard(target, () => false);
    let sawClick = false;
    target.addEventListener("click", () => {
      sawClick = true;
    });

    target.dispatchEvent(new Event("pointerdown"));
    const click = new Event("click", { cancelable: true });
    target.dispatchEvent(click);

    expect(sawClick).toBe(true);
    expect(click.defaultPrevented).toBe(false);
  });

  it("swallows one gesture only: a second, genuine tap right after lands normally", () => {
    const target = new EventTarget();
    let restoring = true;
    installRestoreGuard(target, () => restoring);
    const seen: string[] = [];
    target.addEventListener("click", () => seen.push("click"));

    target.dispatchEvent(new Event("pointerdown")); // armed: the restore is still on
    restoring = false;
    target.dispatchEvent(new Event("click", { cancelable: true })); // swallowed

    target.dispatchEvent(new Event("pointerdown")); // a fresh gesture, restore already over
    target.dispatchEvent(new Event("click", { cancelable: true })); // this one is his

    expect(seen).toEqual(["click"]);
  });

  it("a click with no pointerdown of its own (a keyboard activation) is never armed and never swallowed", () => {
    const target = new EventTarget();
    installRestoreGuard(target, () => true); // the restore is still on, but nothing armed this click
    let sawClick = false;
    target.addEventListener("click", () => {
      sawClick = true;
    });

    target.dispatchEvent(new Event("click", { cancelable: true }));

    expect(sawClick).toBe(true);
  });
});
