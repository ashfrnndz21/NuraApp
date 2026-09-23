import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { NuraCard } from '../components/cards/NuraCard';
import { EmptyState } from '../components/states/EmptyState';
import { getCurrentProfileId } from '../lib/api/config';
import { confirmReviewCard } from '../lib/api/reviewCards';
import { getLastReviewCard } from '../lib/media/pendingPaper';
import type { FieldDecision } from '../domain/reviewCard';

/**
 * Scene 7 (v2 frame 07): the report table, from the review card's own
 * fields — nothing re-computed here, nothing a model wrote. Simplified
 * against the v2 frame: no per-field printed-range slider (`ReviewFieldOut`
 * doesn't carry range bounds over the wire today, only `value`/`unit`/
 * `confidence`/`needs_confirm`/`prompt`) — flagged here rather than
 * invented. An uncertain field (`needsConfirm`) gets its own prompt and a
 * confirm/not-right pair; "Looks right" confirms every field still
 * standing as the extractor read it.
 */
export default function Report() {
  const router = useRouter();
  const card = useMemo(() => getLastReviewCard(), []);
  const [decisions, setDecisions] = useState<Record<string, FieldDecision>>({});
  const [busy, setBusy] = useState(false);

  if (!card) {
    return (
      <View style={styles.screen}>
        <EmptyState
          title="No paper is waiting for a table yet."
          why="Add a paper first and Nura will read it into a table here."
          ctaLabel="Add a paper"
          onPress={() => router.replace('/add-paper')}
          testID="report-empty"
        />
      </View>
    );
  }

  const setDecision = (fieldId: string, decision: FieldDecision) =>
    setDecisions((d) => ({ ...d, [fieldId]: decision }));

  const submit = async () => {
    const profileId = getCurrentProfileId();
    if (!profileId) return;
    setBusy(true);
    try {
      await confirmReviewCard(profileId, card.cardId, {
        decisions: card.fields.map((f) => ({
          fieldId: f.fieldId,
          decision: decisions[f.fieldId] ?? 'confirmed',
        })),
        confirmationId: `${card.cardId}:${Date.now()}`,
      });
      router.push('/insight');
    } finally {
      setBusy(false);
    }
  };

  const outsideCount = card.fields.filter((f) => f.needsConfirm).length;

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.kicker}>
          {card.documentDate ?? ''} {card.source ? `· ${card.source}` : ''}
        </Text>
        <Text style={styles.headline}>
          {outsideCount > 0
            ? `${outsideCount} of ${card.fields.length} need a second look.`
            : `${card.fields.length} readings, all as printed.`}
        </Text>

        {card.fields.map((field) => (
          <NuraCard key={field.fieldId} variant="metric" tier="secondary" testID={`report-field-${field.fieldId}`}>
            <View style={styles.fieldRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldTitle}>{field.attribute}</Text>
                <Text style={styles.fieldSubtitle}>{field.subject}</Text>
              </View>
              <View style={styles.valueBlock}>
                <Text style={styles.valueText}>
                  {String(field.value ?? '—')}
                  {field.unit ? <Text style={styles.unitText}> {field.unit}</Text> : null}
                </Text>
                {field.needsConfirm ? (
                  <View style={styles.flagPill}>
                    <Text style={styles.flagText}>Check this one</Text>
                  </View>
                ) : null}
              </View>
            </View>

            {field.needsConfirm ? (
              <View style={styles.uncertain}>
                {(field.prompt ?? []).map((line, i) => (
                  <Text key={i} style={styles.promptText}>
                    {line}
                  </Text>
                ))}
                <View style={styles.rowButtons}>
                  <Pressable
                    style={[styles.smallBtn, decisions[field.fieldId] === 'confirmed' && styles.smallBtnActive]}
                    onPress={() => setDecision(field.fieldId, 'confirmed')}
                    accessibilityRole="button"
                    accessibilityLabel="This is right"
                    testID={`report-confirm-${field.fieldId}`}
                  >
                    <Text style={styles.smallBtnText}>This is right</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.smallBtn, decisions[field.fieldId] === 'rejected' && styles.smallBtnActive]}
                    onPress={() => setDecision(field.fieldId, 'rejected')}
                    accessibilityRole="button"
                    accessibilityLabel="Not right"
                    testID={`report-reject-${field.fieldId}`}
                  >
                    <Text style={styles.smallBtnText}>Not right</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}
          </NuraCard>
        ))}

        <Text style={styles.caption}>Ranges are the ones printed on your paper. This is not a doctor’s advice.</Text>
      </ScrollView>

      <Pressable
        style={[styles.cta, busy && styles.ctaBusy]}
        disabled={busy}
        onPress={submit}
        accessibilityRole="button"
        accessibilityLabel="Looks right"
        testID="report-confirm-all"
      >
        <Text style={styles.ctaText}>{busy ? 'Saving…' : 'Looks right'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#1f1731', paddingHorizontal: 20, paddingTop: 60 },
  body: { gap: 12, paddingBottom: 20 },
  kicker: { color: 'rgba(251,246,240,0.7)', fontSize: 13 },
  headline: { color: '#fbf6f0', fontSize: 25, fontWeight: '300', lineHeight: 29, marginBottom: 8 },
  fieldRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  fieldTitle: { color: '#fbf6f0', fontSize: 16, fontWeight: '500' },
  fieldSubtitle: { color: 'rgba(251,246,240,0.65)', fontSize: 12.5, marginTop: 2 },
  valueBlock: { alignItems: 'flex-end', gap: 6 },
  valueText: { color: '#fbf6f0', fontSize: 20, fontWeight: '600' },
  unitText: { fontSize: 12, fontWeight: '400', opacity: 0.75 },
  flagPill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, backgroundColor: '#f3b562' },
  flagText: { color: '#231a12', fontSize: 11.5, fontWeight: '600' },
  uncertain: { marginTop: 10, gap: 8 },
  promptText: { color: 'rgba(251,246,240,0.85)', fontSize: 13.5, lineHeight: 18 },
  rowButtons: { flexDirection: 'row', gap: 8 },
  smallBtn: { flex: 1, minHeight: 40, borderRadius: 999, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center' },
  smallBtnActive: { backgroundColor: 'rgba(255,255,255,0.18)' },
  smallBtnText: { color: '#fbf6f0', fontSize: 13 },
  caption: { color: 'rgba(251,246,240,0.55)', fontSize: 12, marginTop: 8 },
  cta: { minHeight: 56, borderRadius: 999, backgroundColor: '#fbf6f0', alignItems: 'center', justifyContent: 'center', marginVertical: 20 },
  ctaBusy: { opacity: 0.7 },
  ctaText: { color: '#2b2140', fontWeight: '600', fontSize: 17 },
});
