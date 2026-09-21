import type { JSX } from "preact";

/** ONE line, replaced in place with a light sweep (docs/design/experience-blueprint.html
 *  `.status`/`think()`) — never an accumulating checklist. Takes the current real step label
 *  (`text`), announces politely to a screen reader, and never stacks: there is only ever one
 *  line here.
 *
 *  Deliberately hookless, like every other component in `web/src/ui/kit/Conversation.tsx`
 *  ("None of them uses a hook, so each renders the same on every call"): the entrance sweep is
 *  played by keying the inner span on `text` itself — when the real step changes, Preact mounts
 *  a fresh span for the new line (CSS `.status-line`, `web/src/ui/kit/kit.css`) rather than this
 *  component tracking an old-line/new-line transition in state. The `aria-live` region is the
 *  OUTER, stable span, so a screen reader announces the change even though the inner span
 *  remounts. Nothing here runs a timer — the sweep and the blur-in are the browser's own CSS
 *  animation clock (`web/src/ui/motion.ts` `STATUS_SWEEP_MS`), started the instant the real
 *  text changes, never before. */
export function StatusLine({ text, className, testId }: { text: string; className?: string; testId?: string }): JSX.Element {
  const cls = className ? `status-line ${className}` : "status-line";
  return (
    <span class="status-line-live" aria-live="polite" data-testid={testId}>
      <span key={text} class={cls}>
        {text}
      </span>
    </span>
  );
}
