# Motion and waiting states

The motion and waiting-states pass (2026-09-18). One principle binds everything below:
**motion shows real state, never fakes time.** Nothing in `web/src/ui/kit` runs an animation on
a timer with no state behind it — no typewriter, no staged reveal on a clock. Every motion here
is triggered by something that really happened: a call went out, a call came back, a stream sent
an event, a step turned done, a finger pressed something, a `State` changed.

Two tokens carry every duration (`web/src/ui/tokens.css`):

- `--settle` (220ms ease-out) — a card, row or answer **entering** after a fetch or a stream
  event.
- `--press` (90ms ease-out) — a **tap**, always shorter than an entrance, so a finger feels an
  instant response.

Both collapse to `0ms` under `prefers-reduced-motion: reduce`, and `web/src/ui/base.css` carries
one global rule that turns every `animation` off outright for `prefers-reduced-motion: reduce`
and narrows every `transition` to `opacity`/`background` only — so a `transform` (a press, a
slide) never runs at all, whatever component it is on. Nothing needs its own reduced-motion
override to be safe; a few components (the skeleton's shimmer, the thinking dots' pulse) also
name themselves in the query so the intent is not left to the general rule alone.

## 1. Every wait shows something honest

**Mechanism:** `web/src/api/client.ts` counts, per request key, how many tagged calls are out
right now (`pendingSignal(key)` / `isPending(key)`) — up the instant `api(path, { key })` is
called (queueing time counts; the person is waiting from the tap, not from when the wire is
free), down however the call settles, success or failure. It is a plain count, not a guess a
screen makes about its own loading state.

`web/src/ui/kit/Pending.tsx`'s `PendingCard` reads that count and is the only thing screens need:

```tsx
<PendingCard requestKey="today" shape="card" lines={3}>
  <TodayCard {...data} />
</PendingCard>
```

While `pendingSignal("today").value > 0`, it draws the kit `SkeletonCard` in the card's own
shape (`shape`: `card` | `tile` | `row`) — never a spinner on a blank page. The moment the count
returns to zero, it draws the real children, wrapped for their entrance (§2).

**The 150ms rule, with no timer:** a call that answers inside 150ms must never flash a skeleton.
`PendingCard` does not decide this with a `setTimeout` — the skeleton's own CSS animation
(`.pending-skeleton`, `web/src/ui/warm.css`) has a 150ms `animation-delay`. A fast answer replaces
the pending node with the real content before the browser ever paints the delayed frame; a slow
one earns the skeleton at the moment it is genuinely still waiting, timed by the browser's own
animation clock, not a component's. This is why the grep test (§6) can require zero `setTimeout`
calls anywhere in `ui/kit` and still get a debounced skeleton.

**Streamed steps:** `Exchange`/`StepTrace`/`ThinkingIndicator` (`web/src/ui/kit/Conversation.tsx`,
pre-existing) draw "Nura is looking" with pulsing dots until the backend's first step arrives,
and each step it really took, ticked when it is really done — never a step the component
invented. These components hold no state and no hook by design (see the file's own docstring);
they draw exactly what the caller's stream handed them, as it arrived.

## 2. Cards enter

- **`.card-enter`** (`web/src/ui/warm.css`): the fade/slide-up a `PendingCard`'s real content
  plays the instant its key stops being pending — `opacity 0→1`, `translateY(6px)→0`, over
  `--settle` (160–220ms band; the token is 220ms, the low end for a component that wants to
  arrive a touch faster). Also available directly on any card or row a screen fades in after a
  fetch or a stream event, without going through `PendingCard`.
- **`.trace-tick`** (`web/src/ui/warm.css`): a "pop" (`tick-pop`, 180ms) the instant a trace
  step's `done` flag really flips — triggered by the class swap from `.trace-spin`, which is
  itself only ever set from the backend's own step data.
- **The wash cross-fade on a `State` change** (`web/src/ui/tokens.css`, pre-existing): the
  `--wash-a/b/c/at` custom properties cross-fade over `--wash-fade` (1200ms) whenever
  `data-posture` on `<html>` changes. Already the one mechanism for this everywhere; this pass
  left it as-is and confirmed it is the only wash transition in the app.

## 3. Tap feedback

Every real tap target presses in — `transform: scale(0.98)` over `--press` (90ms) — on `:active`,
never on `:hover` (a touch has no hover): `.pill`, `.feature-tile`, `.card-button`, `.view-all`,
`button.list-row`, `.arrow-button`, `.insights-card-open` (`web/src/ui/base.css`,
`web/src/ui/warm.css`). Every one of these is already a real `<button>` at `--target` (56px in
the patient density, 48px in the caregiver's) with a `:focus-visible` outline (3px solid Plum);
this pass did not change target sizes or add new focusable elements, only the press feedback and
audited that the existing focus rings cover the same set of targets.

## 4. Captions and answer lines appear exactly when their event arrives

Audited `web/src/ui/kit/Conversation.tsx` (the only place a caption or an answer line is drawn):
no typewriter, no per-character or per-line delay anywhere. `MessageBubble`, `ThinkingIndicator`,
`TraceSteps`, `LookedAt` and `Exchange` hold no state and use no hook — each is a pure function of
its props, so a line is on screen in the same frame the caller received the event for it, and an
answer that has arrived is never held back to let an animation finish (`Exchange`'s own docstring:
"an answer that is there is shown, never held back"). Nothing to change here; this pass confirmed
it and added the grep test (§6) so a future change cannot reintroduce a timer.

## 5. `prefers-reduced-motion: reduce`

- `web/src/ui/base.css`'s global rule turns off every `animation` and narrows every `transition`
  to `opacity`/`background`, for every element — the one rule every animation in this document
  relies on for its reduced-motion behaviour, rather than each one carrying its own override.
- `web/src/ui/tokens.css` additionally collapses `--settle`, `--press` and `--wash-fade` to
  `0ms`, for anywhere a duration is read directly rather than through `animation`/`transition`.
- Named specifically, on top of the general rule, because they are the ones a person is most
  likely to notice moving on its own: `.thinking-dots i` (the "Nura is looking" pulse),
  `.trace-spin` (the in-progress ring), `.skeleton-bar`/`.ask-step-spin`/`.ask-dots i` (the
  shimmer and the ask bar's own dots/spinner).
- Net effect: a skeleton is either there or not, at once, with no shimmer; a press, an entrance
  and a tick still happen (the state change still needs to be reflected) but with no visible
  motion; nothing pulses, turns or shimmers.

## 6. Tests

- `web/tests/unit/client.test.ts` — `pendingSignal`/`isPending`: a tagged call is pending from
  the moment it is made (queueing included) to the moment it settles, on success, on a refusal,
  and on an unreachable network; a different key, or an untagged call, is never touched.
- `web/tests/unit/ui/motion.test.tsx`:
  - `PendingCard`'s pending → Skeleton → content sequence, including two calls sharing a key
    (the Skeleton stands until the count is really back to zero) and that one key's count never
    shows another key's Skeleton.
  - The reduced-motion branch: `--settle`/`--press`/`--wash-fade` collapse to `0ms`, the global
    `animation: none !important` rule is present, and the shimmer/pulse/spin classes are named
    under the query.
  - The grep test: no file under `web/src/ui/kit` calls `setTimeout` — every wait in the kit is a
    signal or a real prop, never a clock of its own.
