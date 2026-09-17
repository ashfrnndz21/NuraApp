import { describe, expect, it, vi } from "vitest";
import { BodySystemsMap } from "../../../src/ui/BodySystemsMap";
import { all, byTestId, byType, hasClass, one, render, text } from "./render";

describe("BodySystemsMap (#175)", () => {
  it("shows nothing when nothing is tagged — no invented glow, no empty filter row", () => {
    expect(render(<BodySystemsMap systems={[]} active={null} onSelect={() => undefined} />)).toEqual([]);
  });

  it("glows only the systems it was given, and offers each as a filter", () => {
    const map = one(<BodySystemsMap systems={["heart", "lungs"]} active={null} onSelect={() => undefined} />);
    const glows = all(map, hasClass("body-map-glow"));
    expect(glows.map((el) => el.props["data-system"]).sort()).toEqual(["heart", "lungs"]);
    // The figure itself is decorative; the row of buttons is the real, accessible control.
    const [figure] = all(map, hasClass("body-map-figure"));
    expect(figure!.props["aria-hidden"]).toBe("true");
    const buttons = all(map, byType("button"));
    expect(buttons.map((b) => text(b))).toEqual(["Heart", "Lungs"]);
  });

  it("says in words what is filtered, and offers a clear way back", () => {
    const filtered = one(<BodySystemsMap systems={["heart"]} active="heart" onSelect={() => undefined} />);
    expect(text(all(filtered, byTestId("body-map-showing")))).toBe("Showing what touches the heart.");
    expect(all(filtered, byTestId("body-map-clear"))).toHaveLength(1);
    const unfiltered = one(<BodySystemsMap systems={["heart"]} active={null} onSelect={() => undefined} />);
    expect(all(unfiltered, byTestId("body-map-showing"))).toHaveLength(0);
    expect(all(unfiltered, byTestId("body-map-clear"))).toHaveLength(0);
  });

  it("tapping the filter for the touched system toggles it, tapping it again clears it", () => {
    const onSelect = vi.fn();
    const map = one(<BodySystemsMap systems={["heart"]} active={null} onSelect={onSelect} />);
    const [heart] = all(map, byTestId("body-map-heart"));
    (heart!.props.onClick as () => void)();
    expect(onSelect).toHaveBeenCalledWith("heart");
    const again = one(<BodySystemsMap systems={["heart"]} active="heart" onSelect={onSelect} />);
    (all(again, byTestId("body-map-heart"))[0]!.props.onClick as () => void)();
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("is read-only in the patient's own density: never the only way to reach the filter", () => {
    const onSelect = vi.fn();
    const map = one(<BodySystemsMap systems={["heart"]} active={null} onSelect={onSelect} readOnly />);
    const [heart] = all(map, byTestId("body-map-heart"));
    expect(heart!.props.disabled).toBe(true);
    // No "show everything" pill either: there is nothing a read-only figure needs to undo.
    expect(all(map, byTestId("body-map-clear"))).toHaveLength(0);
  });
});
