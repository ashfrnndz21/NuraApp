import type { JSX } from "preact";
import { useEffect } from "preact/hooks";
import { afterSignIn, go, screen, signOutHere } from "./flow";
import { focusHeading } from "./ui/focus";
import { emergencyOnly } from "./offline/emergencyCache";
import { EmergencyScreen } from "./screens/Emergency";
import { PapersScreen } from "./screens/Papers";
import { AskScreen } from "./screens/Ask";
import { CardScreen } from "./screens/Card";
import { ClaimScreen, ConsentScreen, DoorsScreen, ForSomeoneScreen } from "./screens/Doors";
import { ConnectScreen } from "./screens/Connect";
import { FamilyScreen } from "./screens/family/Family";
import { HealthScreen } from "./screens/Health";
import { ActivityScreen } from "./screens/Activity";
import { FeedScreen } from "./screens/Feed";
import { MeSheet, ProfileScreen } from "./screens/Me";
import { InsuranceScreen } from "./screens/Insurance";
import { WelcomeScreen } from "./screens/Welcome";
import { VisitsScreen } from "./screens/tabs";
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
import { profile, restored, token, welcomed } from "./store/session";
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
  // A new screen: the screen reader and the keyboard start at its heading (E15-04).
  useEffect(() => focusHeading(), [current.name, welcomed.value]);
  if (!restored.value) return null;
  if (current.name === "loading") {
    if (!token.value) void signOutHere();
    else {
      // Nothing of the remembered papers is drawn until the session is known to be good. The
      // check is one round trip; with no network it fails at once and Today opens from the page
      // the phone kept, which is what a kept page is for. Rendering Today first would put the
      // last person's name in the header on a shared phone whose token has since expired —
      // the same leak as a sign-out that forgets nothing, through the door people actually use.
      afterSignIn().catch((failure: unknown) => {
        // A refused session: back to sign-in, with nothing of theirs left on the phone. Offline
        // or a server error says nothing about the key: Today, from what the phone kept.
        if (afterRestoreFailure(failure) === "signin") return void signOutHere();
        if (profile.value) go({ name: "today" });
        else void signOutHere();
      });
    }
    return null;
  }
  switch (current.name) {
    case "signin":
      // A phone's first sign-in starts at the welcome (docs/design-direction.md).
      return welcomed.value ? <PhoneScreen /> : <WelcomeScreen />;
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
      // A key to the emergency card alone (checkpoint 14's neighbour) sees that card, and nothing else.
      return profile.value && emergencyOnly(profile.value) ? <EmergencyScreen /> : <TodayScreen saved={current.saved ?? false} />;
    case "feed":
      return <FeedScreen />;
    case "ask":
      return <AskScreen item={current.item} question={current.question} />;
    case "reading":
      return <ReadingScreen />;
    case "health":
      return <HealthScreen />;
    case "activity":
      return <ActivityScreen />;
    case "visit":
      return <VisitScreen appointmentId={current.appointmentId} />;
    case "visits":
      return <VisitsScreen />;
    case "record":
      return <RecordScreen at={current.at ?? { name: "hub" }} />;
    case "onboarding":
      return <OnboardingScreen />;
    case "emergency":
      return <EmergencyScreen />;
    case "papers":
      return <PapersScreen report={current.report ?? false} />;
    case "profile":
      return <ProfileScreen />;
    case "insurance":
      return <InsuranceScreen />;
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
    case "connect":
      return <ConnectScreen />;
    case "family":
      return <FamilyScreen part={current.part ?? "home"} />;
  }
}

