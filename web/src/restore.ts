import { Refused, Unreachable } from "./api/client";

/** Where the app lands when the background check on reopening fails (who am I, which doors).
 *
 *  Only a refused session — the token is no longer good — goes back to sign-in. Anything
 *  else — no network, a server error, a busy database while an earlier page's request is
 *  still finishing — keeps him on the Today he was on: the token is still good, and Today
 *  makes its own reads and says its own refusal if one comes. */
export function afterRestoreFailure(failure: unknown): "signin" | "stay" {
  if (failure instanceof Refused && (failure.refusal === "NoSession" || failure.status === 401)) return "signin";
  return "stay";
}

/** What a failed read on Today means. A lost network, or a server that could not answer (a
 *  5xx: a busy database, a deployment restarting), says nothing about his key: the page the
 *  phone kept stays, dated. Only a refusal — the backend said no to this key — deletes what
 *  the phone kept and is said in its sentence. */
export function readFailure(failure: unknown): "network" | "server" | "refused" {
  if (failure instanceof Unreachable) return "network";
  if (failure instanceof Refused && failure.status >= 500) return "server";
  return "refused";
}
