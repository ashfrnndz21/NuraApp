import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { afterSignIn } from "../flow";
import { demo, dev } from "../store/deployment";
import { setToken, setWelcomed } from "../store/session";
import { t } from "../strings";
import { Notice } from "../ui/components";
import { WelcomeIllustration } from "../ui/illustrations";
import { Icon, IconBadge, PillButton, type IconName, type Tint } from "../ui/kit";

/** The two demo/dev shortcuts under Get started, and whether they show at all — a component
 *  of its own, with no hooks, so `demo.value || dev.value` can be checked without a phone's
 *  sign-in machinery (`tests/unit/welcome.test.tsx`). `WelcomeScreen` holds the one piece of
 *  state (which one is signing in, and the last failure) and passes it down. */
export function DemoSignIn({
  show,
  onTry,
  busy,
  error,
}: {
  show: boolean;
  onTry: (who: "pa" | "mei") => void;
  busy: "pa" | "mei" | null;
  error: unknown;
}): JSX.Element | null {
  if (!show) return null;
  const w = t().welcome;
  return (
    <div class="welcome-demo-signin" data-testid="welcome-demo-signin">
      <PillButton
        variant="secondary"
        onClick={() => onTry("pa")}
        disabled={busy !== null}
        testId="welcome-try-pa"
      >
        {w.tryAsPa}
      </PillButton>
      <PillButton
        variant="secondary"
        onClick={() => onTry("mei")}
        disabled={busy !== null}
        testId="welcome-try-mei"
      >
        {w.tryAsMei}
      </PillButton>
      <Notice error={error} />
    </div>
  );
}

/** Welcome, before a phone's first sign-in, as the approved board draws it
 *  (docs/design/nura-concept-board.html, "Welcome"): the picture on its rounded card, the heart
 *  and the serif wordmark, a two-line serif tagline and the line under it, three value tiles, and
 *  a full-width Get started.
 *
 *  Nura has one way in for both a new phone and one that has signed in before — the phone
 *  number — so there is one button, not two that both led to the same place (plain words
 *  review, #237): no name, no papers here, so it is the same on every phone either way.
 *
 *  Demo/dev only (`GET /deployment`, `dev`/`demo` signals): two more buttons underneath, "Try
 *  it as Pa" and "Try it as Mei", sign in at once as the number `app.demo_seed` seeded — no
 *  phone number or code typed. Never shown outside a demo or a dev run. */
export function WelcomeScreen(): JSX.Element {
  const s = t();
  const w = s.welcome;
  const values: { icon: IconName; tint: Tint; title: string; line: string }[] = [
    { icon: "pill", tint: "blush", title: w.remember, line: w.rememberLine },
    { icon: "connect", tint: "lavender", title: w.share, line: w.shareLine },
    { icon: "calendar", tint: "sage", title: w.prepare, line: w.prepareLine },
  ];
  const onward = () => void setWelcomed();
  const [busy, setBusy] = useState<"pa" | "mei" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const tryAs = async (who: "pa" | "mei") => {
    setBusy(who);
    setError(null);
    try {
      const session = await nura.quickSignIn(who);
      await setToken(session.token);
      await afterSignIn();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(null);
    }
  };
  return (
    <main class="screen welcome" data-testid="welcome-screen">
      <div class="welcome-art">
        <WelcomeIllustration class="welcome-illo" cover />
      </div>
      <div class="welcome-brand">
        <span class="welcome-heart" aria-hidden="true">
          <Icon name="heart" />
        </span>
        <h1 class="welcome-word">{s.appName}</h1>
      </div>
      <p class="welcome-tagline">
        <span>{w.tagline1}</span> <span>{w.tagline2}</span>
      </p>
      <p class="welcome-lead">{w.lead}</p>
      <ul class="value-tiles">
        {values.map((value) => (
          <li key={value.title} class="value-tile">
            <IconBadge icon={value.icon} tint={value.tint} />
            <span class="value-title">{value.title}</span>
            <span class="value-line">{value.line}</span>
          </li>
        ))}
      </ul>
      <PillButton variant="primary" onClick={onward} testId="welcome-start">
        {w.start}
      </PillButton>
      <DemoSignIn
        show={demo.value || dev.value}
        onTry={(who) => void tryAs(who)}
        busy={busy}
        error={error}
      />
    </main>
  );
}
