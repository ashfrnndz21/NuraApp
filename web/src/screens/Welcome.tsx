import type { JSX } from "preact";
import { setWelcomed } from "../store/session";
import { t } from "../strings";
import { WelcomeIllustration } from "../ui/illustrations";
import { Icon, IconBadge, PillButton, type IconName, type Tint } from "../ui/kit";

/** Welcome, before a phone's first sign-in, as the approved board draws it
 *  (docs/design/nura-concept-board.html, "Welcome"): the picture on its rounded card, the heart
 *  and the serif wordmark, a two-line serif tagline and the line under it, three value tiles, a
 *  full-width Get started, and "Already have an account? Sign in".
 *
 *  Nura has one way in for both — the phone number — so both go to it. Nothing here is anyone's:
 *  no name, no papers, so it is the same on every phone. */
export function WelcomeScreen(): JSX.Element {
  const s = t();
  const w = s.welcome;
  const values: { icon: IconName; tint: Tint; title: string; line: string }[] = [
    { icon: "pill", tint: "blush", title: w.remember, line: w.rememberLine },
    { icon: "connect", tint: "lavender", title: w.share, line: w.shareLine },
    { icon: "calendar", tint: "sage", title: w.prepare, line: w.prepareLine },
  ];
  const onward = () => void setWelcomed();
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
      <p class="welcome-signin">
        {w.haveAccount}{" "}
        <button type="button" class="link-button" onClick={onward} data-testid="welcome-sign-in">
          {w.signIn}
        </button>
      </p>
    </main>
  );
}
