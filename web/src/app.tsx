import type { JSX } from "preact";
import { afterSignIn, go, screen } from "./flow";
import { AskScreen } from "./screens/Ask";
import { ClaimScreen, ConsentScreen, DoorsScreen, ForSomeoneScreen } from "./screens/Doors";
import { FamilyScreen } from "./screens/family/Family";
import { FeedScreen } from "./screens/Feed";
import { MeScreen } from "./screens/Me";
import { OnboardingScreen } from "./screens/onboarding/Onboarding";
import { ReadingScreen } from "./screens/Reading";
import { CodeScreen, EmailScreen, EmailTokenScreen, PhoneScreen } from "./screens/SignIn";
import { TodayScreen } from "./screens/Today";
import { VisitScreen } from "./screens/Visit";
import { profile, restored, token } from "./store/session";
import { afterRestoreFailure } from "./restore";

/** One screen at a time. On start, the page restores the session and goes to Today at once
 *  when a profile is remembered (offline included), checking the doors in the background. */
export function App(): JSX.Element | null {
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
      return <AskScreen item={current.item} />;
    case "reading":
      return <ReadingScreen />;
    case "visit":
      return <VisitScreen appointmentId={current.appointmentId} />;
    case "me":
      return <MeScreen />;
    case "onboarding":
      return <OnboardingScreen />;
    case "family":
      return <FamilyScreen part={current.part ?? "home"} />;
  }
}
