import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { LoadingState } from '../components/states/LoadingState';
import { ErrorState } from '../components/states/ErrorState';
import { getCurrentProfileId } from '../lib/api/config';
import { streamNuraRun } from '../lib/ai/runClient';
import { getReviewCard, answerReviewCard } from '../lib/api/reviewCards';
import { takeNextPendingPaper, pendingPaperCount, setLastReviewCard, type PendingPaper } from '../lib/media/pendingPaper';
import type { RunEvent } from '../domain/runEvent';
import type { ReviewCard } from '../domain/reviewCard';
import { whoseMismatchLead, whoseQuestion, whoseChips, duplicateLead, duplicateQuestion, duplicateChips } from '../lib/strings/whosePaper';

type Phase = 'reading' | 'clarify' | 'error' | 'done';

/**
 * Scene 6 (v2 frame 06): "Nura reads it" — a real `POST /profiles/{id}/runs`
 * (`intent: 'understand_paper'`) streamed live. The stage line comes only
 * from `TOOL_CALL_START.stage` — never a fake progress bar, never a
 * timer. Whose-paper and the duplicate question are rendered as the
 * conversation shape once the card comes back asking one, from
 * `clarify.mismatched` (a closed field list) only, never the paper's own
 * printed value.
 */
export default function Reading() {
  const router = useRouter();
  const { label } = useLocalSearchParams<{ label?: string }>();
  const [phase, setPhase] = useState<Phase>('reading');
  const [stage, setStage] = useState('Looking at what you sent');
  const [card, setCard] = useState<ReviewCard | null>(null);
  const [errorMsg, setErrorMsg] = useState<{ title: string; why: string } | null>(null);
  const paperRef = useRef<PendingPaper | null>(null);

  useEffect(() => {
    const profileId = getCurrentProfileId();
    const paper = takeNextPendingPaper();
    paperRef.current = paper;
    if (!profileId || !paper) {
      router.replace('/add-paper');
      return;
    }

    const handle = streamNuraRun(
      profileId,
      'understand_paper',
      { kind: paper.contentType === 'application/pdf' ? 'pdf' : 'photo', data: paper.data, content_type: paper.contentType, captured_at: paper.capturedAt },
      async (event: RunEvent) => {
        if (event.type === 'TOOL_CALL_START' && event.stage) {
          setStage(event.stage);
        } else if (event.type === 'RUN_FINISHED') {
          const cardId = (event.result?.card_id as string) ?? null;
          if (!cardId) {
            setPhase('done');
            return;
          }
          const fullCard = await getReviewCard(profileId, cardId);
          setCard(fullCard);
          setPhase(fullCard.clarify ? 'clarify' : 'done');
        } else if (event.type === 'RUN_ERROR') {
          setErrorMsg({ title: "We couldn't read that paper.", why: event.message });
          setPhase('error');
        }
      },
    );

    return () => handle.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const proceedToNext = () => {
    if (pendingPaperCount() > 0) {
      router.replace({ pathname: '/reading', params: { label: 'the next paper' } });
    } else {
      setLastReviewCard(card);
      router.push('/report');
    }
  };

  const answerClarify = async (value: string | null) => {
    if (!card || value === null) return; // "I'm not sure" leaves the card open, no call (D-2's own rule)
    const profileId = getCurrentProfileId();
    if (!profileId) return;
    const updated = await answerReviewCard(profileId, card.cardId, value);
    setCard(updated);
    if (!updated.clarify) proceedToNext();
  };

  if (phase === 'error' && errorMsg) {
    return (
      <View style={styles.screen}>
        <ErrorState title={errorMsg.title} why={errorMsg.why} ctaLabel="Try again" onPress={() => router.replace('/add-paper')} testID="reading-error" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" style={styles.back}>
        <Text style={styles.backGlyph}>‹</Text>
      </Pressable>

      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.userBubbleRow}>
          <View style={styles.userBubble}>
            <Text style={styles.userText}>📄 Read my {label ?? 'paper'}</Text>
          </View>
        </View>

        {phase === 'reading' ? <LoadingState line={stage} testID="reading-loading" /> : null}

        {phase === 'clarify' && card?.clarify ? (
          <ClarifyTurn card={card} onAnswer={answerClarify} />
        ) : null}

        {phase === 'done' ? (
          <View style={styles.assistantRow}>
            <AIOrb size="sm" stateOverride="idle" />
            <Text style={styles.assistantText}>Found it. See what it means next.</Text>
          </View>
        ) : null}
      </ScrollView>

      {phase === 'done' ? (
        <Pressable style={styles.cta} onPress={proceedToNext} accessibilityRole="button" accessibilityLabel="Continue" testID="reading-continue">
          <Text style={styles.ctaText}>Continue</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function ClarifyTurn({ card, onAnswer }: { card: ReviewCard; onAnswer: (value: string | null) => void }) {
  const clarify = card.clarify!;
  const isWhose = clarify.kind === 'whose_paper';
  const lead = isWhose ? whoseMismatchLead(clarify.mismatched) : duplicateLead(clarify.existingAddedOn);
  const question = isWhose ? whoseQuestion : duplicateQuestion;
  const chips = isWhose ? whoseChips : duplicateChips;

  return (
    <View style={styles.assistantRow}>
      <AIOrb size="sm" stateOverride="idle" />
      <View style={{ flex: 1, gap: 10 }}>
        <Text style={styles.assistantText}>{lead}</Text>
        <Text style={styles.assistantText}>{question}</Text>
        <View style={styles.chipRow}>
          {chips.map((c) => (
            <Pressable
              key={c.label}
              style={styles.chip}
              onPress={() => onAnswer(c.value)}
              accessibilityRole="button"
              accessibilityLabel={c.label}
              testID={`clarify-chip-${c.value ?? 'unsure'}`}
            >
              <Text style={styles.chipText}>{c.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#1f1731', paddingHorizontal: 20, paddingTop: 60 },
  back: { width: 46, height: 46, borderRadius: 23, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', backgroundColor: 'rgba(255,255,255,0.10)', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  backGlyph: { color: '#fbf6f0', fontSize: 22 },
  body: { gap: 16, paddingBottom: 20 },
  userBubbleRow: { alignItems: 'flex-end' },
  userBubble: { maxWidth: '82%', paddingVertical: 11, paddingHorizontal: 16, borderRadius: 22, borderBottomRightRadius: 6, backgroundColor: '#fbf6f0' },
  userText: { color: '#2b2140', fontSize: 15.5, lineHeight: 20.9 },
  assistantRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  assistantText: { flex: 1, color: '#fbf6f0', fontSize: 17, fontWeight: '300', lineHeight: 22, marginTop: 6 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 42, paddingHorizontal: 15, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.14)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center' },
  chipText: { color: '#fbf6f0', fontSize: 14 },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: '#fbf6f0', alignItems: 'center', justifyContent: 'center', marginBottom: 40, marginTop: 20 },
  ctaText: { color: '#2b2140', fontWeight: '600', fontSize: 17 },
});
