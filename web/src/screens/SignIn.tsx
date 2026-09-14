import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { afterSignIn, go } from "../flow";
import { setToken } from "../store/session";
import { language, t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";

/** Phone number → code → signed in. One thing per screen; the code never travels back. */
export function PhoneScreen(): JSX.Element {
  const s = t();
  const [phone, setPhone] = useState("+65");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await nura.startPhone(phone.replace(/\s+/g, ""), name.trim() || null, language.value);
      go({ name: "code", phone: phone.replace(/\s+/g, "") });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.signIn.title} />
      <Tile paper>
        <p>{s.signIn.phoneLead}</p>
        <p class="caption">{s.signIn.phoneHint}</p>
        <Field name="phone" label={s.signIn.phoneLabel} value={phone} onInput={setPhone} type="tel" inputMode="tel" autoComplete="tel" />
        <Field name="name" label={s.signIn.nameLabel} value={name} onInput={setName} autoComplete="given-name" />
        <Pill plum onClick={send} disabled={busy || phone.replace(/\D/g, "").length < 8} testId="send-code">
          {s.signIn.sendCode}
        </Pill>
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
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await nura.verifyPhone(phone, code.trim());
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
      <Header title={s.signIn.title} onBack={() => go({ name: "signin" })} />
      <Tile paper>
        <p>{s.signIn.codeLead}</p>
        <p>{s.signIn.codeHint}</p>
        <Field name="code" label={s.signIn.codeLabel} value={code} onInput={setCode} inputMode="numeric" autoComplete="one-time-code" big maxLength={6} />
        <Pill plum onClick={verify} disabled={busy || !/^\d{6}$/.test(code.trim())} testId="verify-code">
          {s.signIn.signInButton}
        </Pill>
        <p class="caption">{s.signIn.codeWorks}</p>
        <p class="caption">{s.signIn.never}</p>
      </Tile>
      <Notice error={error} />
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
