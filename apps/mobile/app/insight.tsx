import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';
import Animated from 'react-native-reanimated';
import { useRouter } from 'expo-router';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { LoadingState } from '../components/states/LoadingState';
import { ErrorState } from '../components/states/ErrorState';
import { ScreenBackground } from '../components/layout/ScreenBackground';
import { phoneTokens, semanticColors } from '../design/colors';
import * as typography from '../design/typography';
import { getCurrentProfileId } from '../lib/api/config';
import { streamPaperInsight, type PaperInsightReport } from '../lib/ai/paperInsightStream';
import { getReviewCardQueue } from '../lib/media/pendingPaper';

/**
 * Scene 8 (v2 frame 08): "what it means" — `POST …/papers/{artifactId}/
 * insight/stream`, the moment the paper is confirmed. The transitional
 * line ("Writing what is worth asking…") is the stream's own `step`
 * events on the orb; the headline and questions are its one `report`
 * event, never a second, separate call.
 *
 * B1: `sharedTransitionTag={paper-${artifactId}}` matches `report.tsx`'s
 * own card — the same object, unfolding across this route, not a cold
 * navigation.
 *
 * Scoped simplification, named rather than hidden: with several papers
 * confirmed in one visit, this screen runs "what it means" for the
 * first of them only. Chaining N insight streams back to back is real
 * work this checkpoint does not yet do — the person reaches Home with
 * one paper explained, the rest already filed in the record.
 */
export default function Insight() {
  const router = useRouter();
  const card = useMemo(() => getReviewCardQueue()[0] ?? null, []);
  const [stage, setStage] = useState('Writing what is worth asking');
  const [report, setReport] = useState<PaperInsightReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const profileId = getCurrentProfileId();
    if (!profileId || !card) return;
    const handle = streamPaperInsight(profileId, card.artifactId, (event) => {
      if (event.type === 'step') setStage(event.label);
      else if (event.type === 'report') setReport(event.report);
      else if (event.type === 'refusal') setError("We couldn't work out what it means yet.");
    });
    return () => handle.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!card) {
    return (
      <ScreenBackground style={styles.screen}>
        <ErrorState title="Nothing to explain yet." why="Read a paper first." ctaLabel="Add a paper" onPress={() => router.replace('/add-paper')} testID="insight-empty" />
      </ScreenBackground>
    );
  }

  if (error) {
    return (
      <ScreenBackground style={styles.screen}>
        <ErrorState title="We couldn't do that right now." why={error} ctaLabel="Continue" onPress={() => router.replace('/home')} testID="insight-error" />
      </ScreenBackground>
    );
  }

  return (
    <ScreenBackground style={styles.screen}>
      <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" style={styles.back}>
        <Text style={styles.backGlyph}>‹</Text>
      </Pressable>

      <ScrollView contentContainerStyle={styles.body}>
        {!report ? (
          <LoadingState line={stage} testID="insight-loading" />
        ) : (
          <>
            <Animated.View style={styles.assistantRow} sharedTransitionTag={`paper-${card.artifactId}`}>
              <AIOrb size="sm" stateOverride="idle" />
              <Text style={styles.headline}>{report.headline}</Text>
            </Animated.View>
            {report.questions.map((q) => (
              <Animated.View key={q.insight_id} style={styles.questionRow}>
                <Text style={styles.questionText}>{q.text}</Text>
              </Animated.View>
            ))}
            {report.boundary.length > 0 ? (
              <Text style={styles.boundary}>{report.boundary.join(' ')}</Text>
            ) : null}
          </>
        )}
      </ScrollView>

      {report ? (
        <Pressable style={styles.cta} onPress={() => router.replace('/home')} accessibilityRole="button" accessibilityLabel="Go to Home" testID="insight-continue">
          <Text style={styles.ctaText}>Go to Home</Text>
        </Pressable>
      ) : null}
    </ScreenBackground>
  );
}

const styles = StyleSheet.create({
  screen: { paddingHorizontal: 20, paddingTop: 60 },
  back: { width: 46, height: 46, borderRadius: 23, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', backgroundColor: 'rgba(255,255,255,0.10)', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  backGlyph: { color: phoneTokens.c, fontSize: typography.fontSize[22] },
  body: { gap: 16, paddingBottom: 20 },
  assistantRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  headline: { flex: 1, color: phoneTokens.c, fontSize: typography.fontSize[25], fontWeight: '300', lineHeight: 30, marginTop: 4 },
  questionRow: { paddingLeft: 40 },
  questionText: { color: 'rgba(251,246,240,0.9)', fontSize: typography.fontSize[15.5], lineHeight: 21, fontWeight: '300' },
  boundary: { color: 'rgba(251,246,240,0.6)', fontSize: typography.fontSize[12.5], marginTop: 8, paddingLeft: 40 },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: phoneTokens.c, alignItems: 'center', justifyContent: 'center', marginVertical: 20 },
  ctaText: { color: semanticColors.inkOnLight, fontWeight: '600', fontSize: typography.fontSize[17] },
});
