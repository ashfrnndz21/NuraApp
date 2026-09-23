import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { startPhoneSignIn, verifyPhoneSignIn } from '../lib/api/auth';
import { ApiRefusalError, errorStateFromRefusal } from '../lib/api/refusals';
import { ErrorState } from '../components/states/ErrorState';

/**
 * Scene 2 (v2 frame 02): the code sign-in flow, over the real
 * `/auth/phone/{start,verify}` routes. Progressive, not the mockup's
 * both-fields-at-once frame: the code field only appears once a code has
 * actually been sent, because a real backend call sits in between —
 * never a fake progress bar, never both fields live before there is
 * really a code to check.
 */
export default function SignIn() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<{ title: string; why: string; ctaLabel: string } | null>(null);

  const sendCode = async () => {
    setBusy(true);
    setRefusal(null);
    try {
      await startPhoneSignIn(phone);
      setCodeSent(true);
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
      <View style={styles.screen}>
        <ErrorState
          title={refusal.title}
          why={refusal.why}
          ctaLabel={refusal.ctaLabel}
          onPress={() => setRefusal(null)}
          testID="sign-in-error"
        />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
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
        {busy ? <ActivityIndicator color="#2b2140" /> : <Text style={styles.ctaText}>Continue</Text>}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#1f1731', paddingHorizontal: 20, paddingTop: 60, paddingBottom: 40 },
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
  backGlyph: { color: '#fbf6f0', fontSize: 22 },
  body: { flex: 1, marginTop: 100, gap: 10 },
  headline: { color: '#fbf6f0', fontSize: 29, fontWeight: '300', lineHeight: 34 },
  label: { color: 'rgba(251,246,240,0.6)', fontSize: 12, letterSpacing: 0.6, marginTop: 20 },
  field: {
    minHeight: 58,
    borderRadius: 20,
    paddingHorizontal: 18,
    backgroundColor: 'rgba(255,255,255,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    color: '#fbf6f0',
    fontSize: 18,
  },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: '#fbf6f0', alignItems: 'center', justifyContent: 'center' },
  ctaBusy: { opacity: 0.7 },
  ctaText: { color: '#2b2140', fontWeight: '600', fontSize: 17 },
});
