import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { startPhoneSignIn, verifyPhoneSignIn } from '../lib/api/auth';
import { ApiRefusalError, errorStateFromRefusal } from '../lib/api/refusals';
import { ErrorState } from '../components/states/ErrorState';
import { ScreenBackground } from '../components/layout/ScreenBackground';
import { phoneTokens, semanticColors } from '../design/colors';
import * as typography from '../design/typography';

/**
 * Scene 2 (v2 frame 02): the code sign-in flow, over the real
 * `/auth/phone/{start,verify}` routes. Progressive, not the mockup's
 * both-fields-at-once frame: the code field only appears once a code has
 * actually been sent, because a real backend call sits in between —
 * never a fake progress bar, never both fields live before there is
 * really a code to check.
 *
 * A-012/A-014: the code's own expiry (`expires_in_seconds`, previously
 * fetched and discarded) is shown as a plain countdown, beside the one
 * safety line every code-sign-in screen owes: Nura will never call to
 * ask for this code. A-013: a wrong code gets its own calm line
 * (`lib/api/refusals.ts`'s `WrongCode` entry), not the generic fallback.
 */
export default function SignIn() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [expiresInSeconds, setExpiresInSeconds] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [refusal, setRefusal] = useState<{ title: string; why: string; ctaLabel: string } | null>(null);

  useEffect(() => {
    if (expiresInSeconds === null) return;
    setSecondsLeft(expiresInSeconds);
    const id = setInterval(() => {
      setSecondsLeft((s) => (s !== null && s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(id);
  }, [expiresInSeconds]);

  const sendCode = async () => {
    setBusy(true);
    setRefusal(null);
    try {
      const result = await startPhoneSignIn(phone);
      setExpiresInSeconds(result.expiresInSeconds);
      setCodeSent(true);
      setCode('');
    } catch (err) {
      if (err instanceof ApiRefusalError) {
        setRefusal(errorStateFromRefusal(err));
      } else {
        setRefusal({ title: "We couldn't reach Nura.", why: 'Check your connection and try again.', ctaLabel: 'Try again' });
      }
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setRefusal(null);
    try {
      await verifyPhoneSignIn(phone, code);
      router.push('/who');
    } catch (err) {
      if (err instanceof ApiRefusalError) {
        setRefusal(errorStateFromRefusal(err));
      } else {
        setRefusal({ title: "That code didn't work.", why: 'Check the code and try again.', ctaLabel: 'Try again' });
      }
    } finally {
      setBusy(false);
    }
  };

  if (refusal) {
    return (
      <ScreenBackground style={styles.screen}>
        <ErrorState
          title={refusal.title}
          why={refusal.why}
          ctaLabel={refusal.ctaLabel}
          onPress={() => setRefusal(null)}
          testID="sign-in-error"
        />
      </ScreenBackground>
    );
  }

  return (
    <ScreenBackground style={styles.screen}>
      <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" style={styles.back}>
        <Text style={styles.backGlyph}>‹</Text>
      </Pressable>

      <View style={styles.body}>
        <Text style={styles.headline}>What number can{'\n'}I reach you on?</Text>

        <Text style={styles.label}>YOUR PHONE NUMBER</Text>
        <TextInput
          value={phone}
          onChangeText={setPhone}
          placeholder="+60 12 345 6789"
          placeholderTextColor="rgba(251,246,240,0.45)"
          keyboardType="phone-pad"
          style={styles.field}
          editable={!codeSent}
          testID="sign-in-phone"
          accessibilityLabel="Your phone number"
        />

        {codeSent ? (
          <>
            <Text style={styles.label}>THE CODE WE SENT YOU</Text>
            <TextInput
              value={code}
              onChangeText={setCode}
              placeholder="000000"
              placeholderTextColor="rgba(251,246,240,0.45)"
              keyboardType="number-pad"
              maxLength={6}
              style={styles.field}
              testID="sign-in-code"
              accessibilityLabel="The code we sent you"
            />
            <Text style={styles.safety} testID="sign-in-safety-line">
              Nura will never call to ask for this code.
            </Text>
            {secondsLeft !== null ? (
              <Text style={styles.expiry} testID="sign-in-expiry">
                {secondsLeft > 0
                  ? `This code is good for ${Math.ceil(secondsLeft / 60)} more minute${Math.ceil(secondsLeft / 60) === 1 ? '' : 's'}.`
                  : 'This code has expired.'}
              </Text>
            ) : null}
            <Pressable onPress={sendCode} accessibilityRole="button" accessibilityLabel="Send a new code" testID="sign-in-resend">
              <Text style={styles.resend}>Send a new code</Text>
            </Pressable>
          </>
        ) : null}
      </View>

      <Pressable
        style={[styles.cta, busy && styles.ctaBusy]}
        disabled={busy || (!codeSent && phone.length < 6) || (codeSent && code.length < 4)}
        onPress={codeSent ? verify : sendCode}
        accessibilityRole="button"
        accessibilityLabel="Continue"
        testID="sign-in-continue"
      >
        {busy ? <ActivityIndicator color={semanticColors.inkOnLight} /> : <Text style={styles.ctaText}>Continue</Text>}
      </Pressable>
    </ScreenBackground>
  );
}

const styles = StyleSheet.create({
  screen: { paddingHorizontal: 20, paddingTop: 60, paddingBottom: 40 },
  back: {
    width: 46,
    height: 46,
    borderRadius: 23,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    backgroundColor: 'rgba(255,255,255,0.10)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backGlyph: { color: phoneTokens.c, fontSize: typography.fontSize[22] },
  body: { flex: 1, marginTop: 100, gap: 10 },
  headline: { color: phoneTokens.c, fontSize: typography.fontSize[29], fontWeight: '300', lineHeight: 34 },
  label: { color: 'rgba(251,246,240,0.6)', fontSize: typography.fontSize[12], letterSpacing: 0.6, marginTop: 20 },
  field: {
    minHeight: 58,
    borderRadius: 20,
    paddingHorizontal: 18,
    backgroundColor: phoneTokens.g,
    borderWidth: 1,
    borderColor: phoneTokens.gb,
    color: phoneTokens.c,
    fontSize: typography.fontSize[18],
  },
  safety: { color: 'rgba(251,246,240,0.7)', fontSize: typography.fontSize[12.5], marginTop: 4 },
  expiry: { color: 'rgba(251,246,240,0.55)', fontSize: typography.fontSize[12] },
  resend: { color: phoneTokens.c, fontSize: typography.fontSize[13.5], fontWeight: '500', marginTop: 4, textDecorationLine: 'underline' },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: phoneTokens.c, alignItems: 'center', justifyContent: 'center' },
  ctaBusy: { opacity: 0.7 },
  ctaText: { color: semanticColors.inkOnLight, fontWeight: '600', fontSize: typography.fontSize[17] },
});
