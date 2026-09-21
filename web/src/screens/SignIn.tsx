import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { afterSignIn, go } from "../flow";
import { setToken } from "../store/session";
import { language, t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";
import { Orb, SoftText, ThreeStateButton } from "../ui/kit";
import { classifySignInError, shouldOfferResend, validCode, validPhone } from "../signin";

/** One line Nura says, beside the small orb (docs/design/experience-blueprint.html `signin`:
 *  "What number can I reach you on?" — one status line, not a form caption). */
function Says({ text, testId }: { text: string; testId?: string }): JSX.Element {
  return (
    <div class="signin-say">
      <Orb size="sm" />
      <SoftText text={text} pace="headline" as="p" className="signin-say-line" testId={testId} />
    </div>
  );
}

/** Phone number → code → signed in, as one conversation step (`signin` scene): Nura's line,
 *  the field, a button that goes through its three real states. Every label and test id a spec
 *  elsewhere already reads (`getByLabel("Your phone number")`, `send-code`) is unchanged — only
 *  how the step is framed changes. */
export function PhoneScreen(): JSX.Element {
  const s = t();
  const [phone, setPhone] = useState("+65");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);

  const send = async () => {
    // A number too short to be real is never sent — the same floor the field's own `disabled`
    // used to hold, kept here now that `ThreeStateButton` has no `disabled` prop of its own.
    // Thrown, not returned: a plain return would resolve the promise `ThreeStateButton` is
    // waiting on and flip it to "done" for nothing sent at all. Nothing is shown for it — a box
    // he has simply not finished typing into yet is not an error.
    if (!validPhone(phone)) throw new Error("phone too short");
    setError(null);
    await nura.startPhone(phone.replace(/\s+/g, ""), name.trim() || null, language.value).then(
      () => go({ name: "code", phone: phone.replace(/\s+/g, "") }),
      (failure: unknown) => {
        setError(failure);
        throw failure;
      },
    );
  };

  return (
    <main class="screen">
      <Header title={s.signIn.title} />
      <Tile paper>
        <div class="signin-step">
          <Says text={s.signIn.phoneLead} testId="signin-say" />
          <p class="caption">{s.signIn.phoneHint}</p>
          <Field name="phone" label={s.signIn.phoneLabel} value={phone} onInput={setPhone} type="tel" inputMode="tel" autoComplete="tel" />
          <Field name="name" label={s.signIn.nameLabel} value={name} onInput={setName} autoComplete="given-name" />
          <ThreeStateButton
            label={s.signIn.sendCode}
            busyLabel={s.signIn.sending}
            doneLabel={s.signIn.sent}
            onAct={send}
            testId="send-code"
          />
        </div>
      </Tile>
      <Notice error={error} />
      <Pill quiet onClick={() => go({ name: "email" })}>
        {s.signIn.useEmail}
      </Pill>
    </main>
  );
}

export function CodeScreen({ phone }: { phone: string }): JSX.Element {
  const s = t();
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [resent, setResent] = useState(false);

  const verify = async () => {
    if (!validCode(code)) throw new Error("code not 6 digits yet");
    setError(null);
    await nura.verifyPhone(phone, code.trim()).then(
      async (session) => {
        await setToken(session.token);
        await afterSignIn();
      },
      (failure: unknown) => {
        setError(failure);
        throw failure;
      },
    );
  };
  const errorKind = error ? classifySignInError(error) : null;

  // A real resend: it asks the backend for a fresh code exactly as the first send did, and
  // shows whatever the backend says — a rate limit included (`ChallengeLocked`) — rather than
  // a client-side countdown of its own (the API gives no cooldown figure to count down from,
  // only `expires_in_seconds` for the code just sent).
  const resend = async () => {
    setError(null);
    setResent(false);
    await nura.startPhone(phone, null, language.value).then(
      () => setResent(true),
      (failure: unknown) => {
        setError(failure);
        throw failure;
      },
    );
  };

  return (
    <main class="screen">
      <Header title={s.signIn.title} onBack={() => go({ name: "signin" })} />
      <Tile paper>
        <div class="signin-step">
          <Says text={s.signIn.codeLead} testId="signin-say" />
          <p>{s.signIn.codeHint}</p>
          <Field name="code" label={s.signIn.codeLabel} value={code} onInput={setCode} inputMode="numeric" autoComplete="one-time-code" big maxLength={6} />
          <ThreeStateButton
            label={s.signIn.signInButton}
            busyLabel={s.signIn.checking}
            doneLabel={s.signIn.signedIn}
            onAct={verify}
            testId="verify-code"
          />
          <p class="caption">{s.signIn.codeWorks}</p>
          <p class="caption">{s.signIn.never}</p>
          <Pill
            quiet={!(errorKind && shouldOfferResend(errorKind))}
            plum={Boolean(errorKind && shouldOfferResend(errorKind))}
            onClick={() => void resend()}
            testId="resend-code"
            extraClass="signin-resend"
          >
            {s.signIn.resend}
          </Pill>
          {resent && (
            <p class="caption" role="status" data-testid="resend-done">
              {s.signIn.resendDone}
            </p>
          )}
        </div>
      </Tile>
      <Notice error={error} errorKind={errorKind ?? undefined} />
    </main>
  );
}

/** The email link: the same shape, with the token from the message typed in. */
export function EmailScreen(): JSX.Element {
  const s = t();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await nura.startEmail(email.trim(), name.trim() || null, language.value);
      go({ name: "emailToken", email: email.trim() });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.signIn.title} onBack={() => go({ name: "signin" })} />
      <Tile paper>
        <p>{s.signIn.emailLead}</p>
        <Field name="email" label={s.signIn.emailLabel} value={email} onInput={setEmail} type="email" inputMode="email" autoComplete="email" />
        <Field name="name" label={s.signIn.nameLabel} value={name} onInput={setName} autoComplete="given-name" />
        <Pill plum onClick={send} disabled={busy || !email.includes("@")}>
          {s.signIn.sendLink}
        </Pill>
      </Tile>
      <Notice error={error} />
      <Pill quiet onClick={() => go({ name: "signin" })}>
        {s.signIn.usePhone}
      </Pill>
    </main>
  );
}

export function EmailTokenScreen({ email }: { email: string }): JSX.Element {
  const s = t();
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await nura.verifyEmail(email, code.trim());
      await setToken(session.token);
      await afterSignIn();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.signIn.title} onBack={() => go({ name: "email" })} />
      <Tile paper>
        <p>{s.signIn.linkLead}</p>
        <p>{s.signIn.linkHint}</p>
        <Field name="token" label={s.signIn.linkLabel} value={code} onInput={setCode} autoComplete="one-time-code" />
        <Pill plum onClick={verify} disabled={busy || code.trim().length === 0}>
          {s.signIn.signInButton}
        </Pill>
        <p class="caption">{s.signIn.codeWorks}</p>
      </Tile>
      <Notice error={error} />
    </main>
  );
}
