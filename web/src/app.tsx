import type { JSX } from "preact";
import { afterSignIn, go, screen } from "./flow";
import { ClaimScreen, ConsentScreen, DoorsScreen, ForSomeoneScreen } from "./screens/Doors";
import { MeScreen } from "./screens/Me";
import { ReadingScreen } from "./screens/Reading";
import { CodeScreen, EmailScreen, EmailTokenScreen, PhoneScreen } from "./screens/SignIn";
import { TodayScreen } from "./screens/Today";
import { profile, restored, token } from "./store/session";
import { Unreachable } from "./api/client";

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
        // Offline: stay on the remembered Today. A refused token: back to sign-in.
        if (!(failure instanceof Unreachable)) go({ name: "signin" });
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
      return <DoorsScreen doors={current.doors} />;
    case "consent":
      return <ConsentScreen />;
    case "claim":
      return <ClaimScreen offer={current.offer} />;
    case "forSomeone":
      return <ForSomeoneScreen />;
    case "today":
      return <TodayScreen saved={current.saved ?? false} />;
    case "reading":
      return <ReadingScreen />;
    case "me":
      return <MeScreen />;
  }
}
