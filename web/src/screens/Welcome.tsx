import type { JSX } from "preact";
import { setWelcomed } from "../store/session";
import { t } from "../strings";
import { WelcomeIllustration } from "../ui/illustrations";
import { IconBadge, PillButton, Wordmark, type Tint } from "../ui/kit";
import type { IconName } from "../ui/kit";

/** Welcome (docs/design-direction.md, Reference B's first screen), before a phone's first
 *  sign-in: the picture, the mark and the serif wordmark, a two-line tagline in Nura's own plain
 *  words and the line under it, three value tiles, one solid Get started and a quiet Sign in.
 *
 *  Nura has one way in for both — the phone number — so both go to it. Nothing here is anyone's:
 *  no name, no papers, so it is the same on every phone. */
export function WelcomeScreen(): JSX.Element {
  const s = t();
  const w = s.welcome;
  const values: { icon: IconName; tint: Tint; title: string; line: string }[] = [
    { icon: "easy", tint: "butter", title: w.simple, line: w.simpleLine },
    { icon: "connect", tint: "sage", title: w.family, line: w.familyLine },
    { icon: "privacy", tint: "lavender", title: w.private, line: w.privateLine },
  ];
  const onward = () => void setWelcomed();
  return (
    <main class="screen welcome" data-testid="welcome-screen">
      <div class="welcome-art">
        <WelcomeIllustration class="welcome-illo" />
      </div>
      <div class="welcome-body">
        <Wordmark name={s.appName} size="large" as="h1" />
        <p class="welcome-tagline">
          <span>{w.tagline1}</span> <span>{w.tagline2}</span>
        </p>
        <p class="welcome-lead">{w.lead}</p>
        <ul class="value-tiles">
          {values.map((value) => (
            <li key={value.title} class="value-tile" data-tint={value.tint}>
              <IconBadge icon={value.icon} tint="paper" shape="circle" />
              <span class="value-title">{value.title}</span>
              <span class="value-line">{value.line}</span>
            </li>
          ))}
        </ul>
        <PillButton variant="primary" onClick={onward} testId="welcome-start">
          {w.start}
        </PillButton>
        <PillButton variant="quiet" onClick={onward} testId="welcome-sign-in">
          {w.signIn}
        </PillButton>
      </div>
    </main>
  );
}
