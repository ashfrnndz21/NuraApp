import type { JSX } from "preact";
import { afterSignIn, go, screen } from "./flow";
import { AskScreen } from "./screens/Ask";
import { CardScreen } from "./screens/Card";
import { EmergencyScreen } from "./screens/Emergency";
import { ClaimScreen, ConsentScreen, DoorsScreen, ForSomeoneScreen } from "./screens/Doors";
import { FamilyScreen } from "./screens/family/Family";
import { FeedScreen } from "./screens/Feed";
import { MeSheet } from "./screens/Me";
import { PlanScreen, VisitsScreen } from "./screens/tabs";
import { OnboardingScreen } from "./screens/onboarding/Onboarding";
import { ReadingScreen } from "./screens/Reading";
import { RecordScreen } from "./screens/record/Record";
import { CodeScreen, EmailScreen, EmailTokenScreen, PhoneScreen } from "./screens/SignIn";
import { TodayScreen } from "./screens/Today";
import { VisitScreen } from "./screens/Visit";
import { BriefScreen } from "./screens/Brief";
import { FeelingScreen } from "./screens/Feeling";
import { NotWellScreen } from "./screens/NotWell";
import { QuestionsScreen } from "./screens/Questions";
import { SymptomsScreen } from "./screens/Symptoms";
import { WhatToDoScreen } from "./screens/WhatToDo";
import { profile, restored, token } from "./store/session";
import { afterRestoreFailure } from "./restore";

/** One screen at a time. On start, the page restores the session and goes to Today at once
 *  when a profile is remembered (offline included), checking the doors in the background. */
export function App(): JSX.Element | null {
  const shown = Route();
  // Me is a sheet over whatever screen is open (D1), never a screen of its own.
  return shown && (
    <>
      {shown}
      <MeSheet />
    </>
  );
}

function Route(): JSX.Element | null {
  const current = screen.value;
  if (!restored.value) return null;
  if (current.name === "loading") {
    if (!token.value) go({ name: "signin" });
    else if (profile.value) {
      go({ name: "today" });
      afterSignIn().catch((failure: unknown) => {
        // A refused session: back to sign-in. Offline, a server error: stay on Today.
        if (afterRestoreFailure(failure) === "signin") go({ name: "signin" });
      });
    } else afterSignIn().catch(() => go({ name: "signin" }));
    return null;
  }
  switch (current.name) {
    case "signin":
      return <PhoneScreen />;
    case "code":
      return <CodeScreen phone={current.phone} />;
    case "email":
      return <EmailScreen />;
    case "emailToken":
      return <EmailTokenScreen email={current.email} />;
    case "doors":
      return <DoorsScreen doors={current.doors} refusal={current.refusal} />;
    case "consent":
      return <ConsentScreen />;
    case "claim":
      return <ClaimScreen offer={current.offer} />;
    case "forSomeone":
      return <ForSomeoneScreen />;
    case "today":
      return <TodayScreen saved={current.saved ?? false} />;
    case "feed":
      return <FeedScreen />;
    case "ask":
      return <AskScreen item={current.item} question={current.question} />;
    case "reading":
      return <ReadingScreen />;
    case "visit":
      return <VisitScreen appointmentId={current.appointmentId} />;
    case "visits":
      return <VisitsScreen />;
    case "plan":
      return <PlanScreen />;
    case "record":
      return <RecordScreen at={current.at ?? { name: "hub" }} />;
    case "onboarding":
      return <OnboardingScreen />;
    case "notWell":
      return <NotWellScreen />;
    case "whatToDo":
      return <WhatToDoScreen lines={current.lines} offline={current.offline} refusal={current.refusal} />;
    case "feeling":
      return <FeelingScreen tap={current.tap} />;
    case "symptoms":
      return <SymptomsScreen />;
    case "brief":
      return <BriefScreen appointmentId={current.appointmentId} />;
    case "questions":
      return <QuestionsScreen appointmentId={current.appointmentId} />;
    case "card":
      return <CardScreen item={current.item} />;
    case "emergency":
      return <EmergencyScreen />;
    case "family":
      return <FamilyScreen part={current.part ?? "home"} />;
  }
}
