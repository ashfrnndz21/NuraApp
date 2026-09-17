/** #142: for about a second after the app reopens, the restore check (`afterSignIn`, W1) can
 *  land on Today under a finger that was already resting on the screen — nothing is drawn until
 *  the session is known to be good, on purpose (`app.tsx`'s own comment: a shared phone must
 *  never show a stale session's papers first), so a gesture that began on that blank screen was
 *  aimed at nothing, and its lift-off must not resolve into whatever Today control the browser
 *  now finds under it once the restore lands and the screen fills in.
 *
 *  One gesture is watched at a time: a `pointerdown` while `restoring()` is still true arms it;
 *  the `click` that gesture produces, wherever the screen has moved to by the time it fires, is
 *  swallowed here, before Preact's own handlers ever see it — no tap read as his, no request
 *  sent for it. A gesture that starts once the restore is over is untouched, at once: there is
 *  no delay to wait out, only a finger that was already down before there was anything to press. */
export function installRestoreGuard(target: Pick<EventTarget, "addEventListener">, restoring: () => boolean): void {
  let armed = false;
  target.addEventListener(
    "pointerdown",
    () => {
      armed = restoring();
    },
    { capture: true },
  );
  target.addEventListener(
    "click",
    (event) => {
      if (!armed) return;
      armed = false;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    },
    { capture: true },
  );
}
