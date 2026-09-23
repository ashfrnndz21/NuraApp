import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { LoadingState } from '../components/states/LoadingState';
import { ErrorState } from '../components/states/ErrorState';
import { getCurrentProfileId } from '../lib/api/config';
import { streamPaperInsight, type PaperInsightReport } from '../lib/ai/paperInsightStream';
import { getLastReviewCard } from '../lib/media/pendingPaper';

/**
 * Scene 8 (v2 frame 08): "what it means" — `POST …/papers/{artifactId}/
 * insight/stream`, the moment the paper is confirmed. The transitional
 * line ("Writing what is worth asking…") is the stream's own `step`
 * events on the orb; the headline and questions are its one `report`
 * event, never a second, separate call.
 */
export default function Insight() {
  const router = useRouter();
  const card = useMemo(() => getLastReviewCard(), []);
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
      <View style={styles.screen}>
        <ErrorState title="Nothing to explain yet." why="Read a paper first." ctaLabel="Add a paper" onPress={() => router.replace('/add-paper')} testID="insight-empty" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.screen}>
        <ErrorState title="We couldn't do that right now." why={error} ctaLabel="Continue" onPress={() => router.replace('/home')} testID="insight-error" />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back" style={styles.back}>
        <Text style={styles.backGlyph}>‹</Text>
      </Pressable>

      <ScrollView contentContainerStyle={styles.body}>
        {!report ? (
          <LoadingState line={stage} testID="insight-loading" />
        ) : (
          <>
            <View style={styles.assistantRow}>
              <AIOrb size="sm" stateOverride="idle" />
              <Text style={styles.headline}>{report.headline}</Text>
            </View>
            {report.questions.map((q) => (
              <View key={q.insight_id} style={styles.questionRow}>
                <Text style={styles.questionText}>{q.text}</Text>
              </View>
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
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#1f1731', paddingHorizontal: 20, paddingTop: 60 },
  back: { width: 46, height: 46, borderRadius: 23, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', backgroundColor: 'rgba(255,255,255,0.10)', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  backGlyph: { color: '#fbf6f0', fontSize: 22 },
  body: { gap: 16, paddingBottom: 20 },
  assistantRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  headline: { flex: 1, color: '#fbf6f0', fontSize: 25, fontWeight: '300', lineHeight: 30, marginTop: 4 },
  questionRow: { paddingLeft: 40 },
  questionText: { color: 'rgba(251,246,240,0.9)', fontSize: 15.5, lineHeight: 21, fontWeight: '300' },
  boundary: { color: 'rgba(251,246,240,0.6)', fontSize: 12.5, marginTop: 8, paddingLeft: 40 },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: '#fbf6f0', alignItems: 'center', justifyContent: 'center', marginVertical: 20 },
  ctaText: { color: '#2b2140', fontWeight: '600', fontSize: 17 },
});
