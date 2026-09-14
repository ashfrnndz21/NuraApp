import type { JSX } from "preact";
import { stage } from "../../onboarding/state";
import { AboutStep } from "./About";
import { AsksStep } from "./Asks";
import { CloudStep } from "./Cloud";
import { InviteStep } from "./Invite";
import { PlanStep } from "./Plan";
import { QuestionsStep } from "./Questions";
import { ReadBackStep } from "./ReadBack";
import { RecordsStep, ReviewStep } from "./Records";

/** Onboarding (TASKS.md Session 12, on the web per ADR 0001): about you, the word cloud, the
 *  follow-up questions, the read-back, the papers with their review cards, the questions the
 *  papers raise, and the gaps. One step at a time; no tab bar until it is done. */
export function OnboardingScreen(): JSX.Element {
  const current = stage.value;
  switch (current.name) {
    case "about":
      return <AboutStep only={current.only} />;
    case "cloud":
      return <CloudStep />;
    case "asks":
      return <AsksStep only={current.only} />;
    case "readBack":
      return <ReadBackStep />;
    case "records":
      return <RecordsStep />;
    case "review":
      return <ReviewStep key={current.card.card_id} card={current.card} />;
    case "questions":
      return <QuestionsStep />;
    case "plan":
      return <PlanStep />;
    case "invite":
      return <InviteStep />;
  }
}
