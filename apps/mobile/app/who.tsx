import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { busyHold } from '../design/motion';
import { getConsentWording } from '../lib/api/consent';
import { createOwnProfile, createProfileForSomeone, getMe, type Relationship } from '../lib/api/profile';
import { ApiRefusalError, errorStateFromRefusal } from '../lib/api/refusals';
import { ErrorState } from '../components/states/ErrorState';

type Who = 'me' | 'parent' | 'someone_else';

interface Turn {
  id: string;
  role: 'assistant' | 'user';
  text: string;
}

/**
 * Scene 3 (v2 frame 03): "who is this for" as the spec's conversation
 * shape — never a form. Three chips answer Nura's first question; the
 * name (and, for someone else, the patient's own phone — required by
 * the real `POST /profiles/for-someone`) is collected the same
 * conversational way, one line at a time, ending in `POST /profiles/mine`
 * or `POST /profiles/for-someone` for real.
 */
export default function WhoIsThisFor() {
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([
    { id: 't0', role: 'assistant', text: 'Hello. I am Nura. Who am I looking after?' },
  ]);
  const [who, setWho] = useState<Who | null>(null);
  const [stage, setStage] = useState<'chips' | 'name' | 'patient_phone' | 'done'>('chips');
  const [draft, setDraft] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<{ title: string; why: string; ctaLabel: string } | null>(null);

  const relationshipFor = (w: Who): Relationship => (w === 'parent' ? 'other_family' : 'other');
  const chipLabel = (w: Who) => (w === 'me' ? 'Me' : w === 'parent' ? 'My parent' : 'Someone else');

  const pickWho = (w: Who) => {
    setWho(w);
    setTurns((t) => [...t, { id: `who-${w}`, role: 'user', text: chipLabel(w) }]);
    setStage('name');
  };

  const finishAsOwner = async (finalName: string) => {
    const wording = await getConsentWording('en');
    const profile = await createOwnProfile(
      { wordingVersion: wording.version, language: wording.language, capturedVia: 'app' },
      { displayName: finalName, language: wording.language },
    );
    return profile;
  };

  const finishForSomeone = async (finalName: string, patientPhone: string, w: Who) => {
    const wording = await getConsentWording('en');
    return createProfileForSomeone(
      patientPhone,
      finalName,
      relationshipFor(w),
      { wordingVersion: wording.version, language: wording.language, capturedVia: 'app' },
      { language: wording.language },
    );
  };

  const submitDraft = async () => {
    const value = draft.trim();
    if (!value || !who) return;
    setTurns((t) => [...t, { id: `d-${t.length}`, role: 'user', text: value }]);
    setDraft('');

    if (stage === 'name') {
      setName(value);
      if (who === 'me') {
        setBusy(true);
        try {
          await finishAsOwner(value);
          setTurns((t) => [...t, { id: `ok-${t.length}`, role: 'assistant', text: `Good to meet you, ${value}.` }]);
          setStage('done');
          setTimeout(() => router.replace('/home'), busyHold);
        } catch (err) {
          if (err instanceof ApiRefusalError && err.refusal === 'ProfileAlreadyOwned') {
            // A real, legitimate outcome (a returning account), never an error — recognise
            // the existing profile via /me and continue, instead of showing ErrorState.
            const me = await getMe();
            setTurns((t) => [...t, { id: `ok-${t.length}`, role: 'assistant', text: `Welcome back, ${me.displayName}.` }]);
            setStage('done');
            setTimeout(() => router.replace('/home'), busyHold);
          } else {
            setRefusal(
              err instanceof ApiRefusalError
                ? errorStateFromRefusal(err)
                : { title: "We couldn't set that up.", why: 'Nothing was saved. Try again.', ctaLabel: 'Try again' },
            );
          }
        } finally {
          setBusy(false);
        }
      } else {
        setTurns((t) => [
          ...t,
          { id: `ask-phone-${t.length}`, role: 'assistant', text: `What number can I reach ${value} on?` },
        ]);
        setStage('patient_phone');
      }
      return;
    }

    if (stage === 'patient_phone' && who) {
      setBusy(true);
      try {
        await finishForSomeone(name, value, who);
        setTurns((t) => [...t, { id: `ok-${t.length}`, role: 'assistant', text: `Good to meet you both. I'll be looking after ${name}.` }]);
        setStage('done');
        setTimeout(() => router.replace('/home'), busyHold);
      } catch (err) {
        setRefusal(
          err instanceof ApiRefusalError
            ? errorStateFromRefusal(err)
            : { title: "We couldn't set that up.", why: 'Nothing was saved. Try again.', ctaLabel: 'Try again' },
        );
      } finally {
        setBusy(false);
      }
    }
  };

  if (refusal) {
    return (
      <View style={styles.screen}>
        <ErrorState title={refusal.title} why={refusal.why} ctaLabel={refusal.ctaLabel} onPress={() => setRefusal(null)} testID="who-error" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.turns}>
        {turns.map((turn) =>
          turn.role === 'assistant' ? (
            <View key={turn.id} style={styles.assistantRow}>
              <AIOrb size="sm" stateOverride="idle" />
              <Text style={styles.assistantText}>{turn.text}</Text>
            </View>
          ) : (
            <View key={turn.id} style={styles.userBubble}>
              <Text style={styles.userText}>{turn.text}</Text>
            </View>
          ),
        )}

        {stage === 'chips' ? (
          <View style={styles.chipRow}>
            {(['me', 'parent', 'someone_else'] as Who[]).map((w) => (
              <Pressable key={w} style={styles.chip} onPress={() => pickWho(w)} accessibilityRole="button" accessibilityLabel={chipLabel(w)} testID={`who-chip-${w}`}>
                <Text style={styles.chipText}>{chipLabel(w)}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
      </ScrollView>

      {(stage === 'name' || stage === 'patient_phone') && !busy ? (
        <View style={styles.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder={stage === 'name' ? 'Type your reply' : 'Their phone number'}
            placeholderTextColor="rgba(251,246,240,0.45)"
            style={styles.input}
            onSubmitEditing={submitDraft}
            testID="who-composer-input"
            accessibilityLabel={stage === 'name' ? 'Your reply' : "Their phone number"}
          />
          <Pressable onPress={submitDraft} accessibilityRole="button" accessibilityLabel="Send" style={styles.send} testID="who-composer-send">
            <Text style={styles.sendText}>→</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#1f1731', paddingHorizontal: 20, paddingTop: 60 },
  turns: { gap: 16, paddingBottom: 20 },
  assistantRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  assistantText: { flex: 1, color: '#fbf6f0', fontSize: 20, fontWeight: '300', lineHeight: 25, marginTop: 6 },
  userBubble: { alignSelf: 'flex-end', maxWidth: '82%', paddingVertical: 11, paddingHorizontal: 16, borderRadius: 22, borderBottomRightRadius: 6, backgroundColor: '#fbf6f0' },
  userText: { color: '#2b2140', fontSize: 15.5, lineHeight: 20.9 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 42, paddingHorizontal: 15, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.14)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center' },
  chipText: { color: '#fbf6f0', fontSize: 14 },
  composer: { flexDirection: 'row', gap: 8, paddingVertical: 16, alignItems: 'center' },
  input: { flex: 1, minHeight: 48, borderRadius: 999, paddingHorizontal: 18, backgroundColor: 'rgba(255,255,255,0.10)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', color: '#fbf6f0', fontSize: 15.5 },
  send: { width: 48, height: 48, borderRadius: 24, backgroundColor: '#fbf6f0', alignItems: 'center', justifyContent: 'center' },
  sendText: { color: '#2b2140', fontSize: 18, fontWeight: '600' },
});
