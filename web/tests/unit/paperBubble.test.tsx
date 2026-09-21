// @vitest-environment happy-dom
import { render } from "preact";
import { afterEach, describe, expect, it } from "vitest";
import { PaperBubble } from "../../src/screens/onboarding/PaperReading";

/** A picture the browser cannot draw must never show as a broken image (found by the owner on
 *  2026-09-21). Needs a real DOM: the fallback is driven by the image's own `error` event. */
const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 20));
let host: HTMLElement | null = null;
function mount(node: Parameters<typeof render>[0]): HTMLElement {
  host = document.createElement("div");
  document.body.appendChild(host);
  render(node, host);
  return host;
}
afterEach(() => {
  if (host) {
    render(null, host);
    host.remove();
    host = null;
  }
});

describe("PaperBubble", () => {
  it("shows the thumbnail for a photo", () => {
    const el = mount(<PaperBubble name="report.jpg" thumb="blob:ok" />);
    expect(el.querySelector('[data-testid="paper-thumb"]')).not.toBeNull();
  });

  it("falls back to the document icon when the picture cannot be drawn, never a broken image", async () => {
    const el = mount(<PaperBubble name="report.heic" thumb="blob:cannot-draw" />);
    el.querySelector('[data-testid="paper-thumb"]')!.dispatchEvent(new Event("error"));
    await flush();
    expect(el.querySelector('[data-testid="paper-thumb"]')).toBeNull();
    expect(el.querySelector("svg")).not.toBeNull();
    expect(el.textContent).toContain("report.heic");
  });

  it("shows the document icon for a PDF", () => {
    const el = mount(<PaperBubble name="report.pdf" />);
    expect(el.querySelector('[data-testid="paper-thumb"]')).toBeNull();
    expect(el.querySelector("svg")).not.toBeNull();
  });
});
