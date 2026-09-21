import { Refused, Unreachable } from "./api/client";

/** Sign in's own small state machine, apart from the screens (`src/screens/SignIn.tsx`), so it
 *  is unit-tested on its own (`tests/unit/signin.test.ts`). Nothing here calls the network or
 *  touches a signal — it only decides two things a screen needs: whether what he has typed is
 *  worth sending, and which real state a refusal from the backend names, so the screen can show
 *  the backend's own sentence (`Notice`, `strings/index.ts` `refusalLines`) rather than a
 *  guessed one and, for a locked or expired code, point at Resend rather than at the box he
 *  already filled in correctly. */

/** A phone number worth sending: the digits alone are at least 8 long, the same floor
 *  `PhoneScreen` always used, kept here so it is not only encoded in a JSX `disabled` prop. */
export function validPhone(phone: string): boolean {
  return phone.replace(/\D/g, "").length >= 8;
}

/** The 6 digits a code always is (`ChallengeOut`, the backend's own shape). */
export function validCode(code: string): boolean {
  return /^\d{6}$/.test(code.trim());
}

export type SignInErrorKind = "wrongCode" | "expired" | "locked" | "noChallenge" | "network" | "other";

/** Which real state a sign-in failure names — the backend's own refusal class where there is
 *  one (`WrongCode`, `ChallengeExpired`, `ChallengeLocked`, `NoOpenChallenge`), a network
 *  failure where the request never reached it, or `"other"` for anything else. Never invents a
 *  state the backend did not report. */
export function classifySignInError(error: unknown): SignInErrorKind {
  if (error instanceof Unreachable) return "network";
  if (error instanceof Refused) {
    switch (error.refusal) {
      case "WrongCode":
        return "wrongCode";
      case "ChallengeExpired":
        return "expired";
      case "ChallengeLocked":
        return "locked";
      case "NoOpenChallenge":
        return "noChallenge";
      default:
        return "other";
    }
  }
  return "other";
}

/** Whether this failure is one Resend genuinely answers (the code is gone, not merely
 *  mistyped) — used only to decide which action to point at, never to hide the backend's own
 *  words, which `Notice` always shows regardless. */
export function shouldOfferResend(kind: SignInErrorKind): boolean {
  return kind === "expired" || kind === "locked" || kind === "noChallenge";
}
