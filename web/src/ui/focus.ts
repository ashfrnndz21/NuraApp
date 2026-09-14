/** Move focus to the first heading of the screen now up (E15-04), so a screen reader reads the
 *  new screen from its top and Tab goes on from there, not from where the last screen's button
 *  was. The heading takes focus without a ring and without scrolling. */
export function focusHeading(): void {
  if (typeof document === "undefined" || typeof requestAnimationFrame === "undefined") return;
  requestAnimationFrame(() => {
    const heading = document.querySelector<HTMLElement>("main h1");
    if (!heading || heading.contains(document.activeElement)) return;
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  });
}
