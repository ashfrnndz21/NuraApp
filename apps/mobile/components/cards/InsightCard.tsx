import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { CardAccentDot, NuraCard } from './NuraCard';

export interface InsightCardProps {
  title: string;
  segments?: readonly [string, string];
  date: { day: string; month: string };
  body: string;
  ctaLabel: string;
  onPressCta: () => void;
  enterIndex?: number;
  staggerMs?: number;
}

/**
 * Home's primary insight card (spec §4): label + optional segmented
 * control, a date chip, the concise insight, one integrated CTA.
 */
export function InsightCard({
  title,
  segments,
  date,
  body,
  ctaLabel,
  onPressCta,
  enterIndex,
  staggerMs,
}: InsightCardProps) {
  const [segment, setSegment] = useState(0);

  return (
    <NuraCard variant="insight" tier="primary" enterIndex={enterIndex} staggerMs={staggerMs} testID="insight-card">
      <View style={styles.row}>
        <View style={styles.titleRow}>
          <CardAccentDot variant="insight" />
          <Text style={styles.title}>{title}</Text>
        </View>
        {segments ? (
          <View style={styles.seg}>
            {segments.map((label, i) => (
              <Pressable key={label} onPress={() => setSegment(i)} hitSlop={6}>
                <Text style={[styles.segLabel, i === segment && styles.segLabelActive]}>{label}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
      </View>
      <View style={styles.body}>
        <View style={styles.date}>
          <Text style={styles.dateDay}>{date.day}</Text>
          <Text style={styles.dateMonth}>{date.month}</Text>
        </View>
        <Text style={styles.bodyText}>{body}</Text>
      </View>
      <Pressable onPress={onPressCta} style={styles.cta} accessibilityRole="button" accessibilityLabel={ctaLabel}>
        <Text style={styles.ctaText}>{ctaLabel}</Text>
      </Pressable>
    </NuraCard>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 },
  title: { color: '#fbf6f0', fontSize: 18, fontWeight: '400' },
  seg: { flexDirection: 'row', gap: 4 },
  segLabel: {
    color: 'rgba(251,246,240,0.7)',
    fontSize: 12,
    paddingVertical: 6,
    paddingHorizontal: 8,
  },
  segLabelActive: {
    color: '#2b2140',
    backgroundColor: '#fbf6f0',
    borderRadius: 999,
    fontWeight: '600',
    overflow: 'hidden',
  },
  body: { flexDirection: 'row', gap: 13, alignItems: 'flex-start' },
  date: {
    width: 50,
    paddingVertical: 7,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.16)',
    alignItems: 'center',
  },
  dateDay: { color: '#fbf6f0', fontSize: 22, lineHeight: 24, fontWeight: '600' },
  dateMonth: { color: 'rgba(251,246,240,0.85)', fontSize: 11.5 },
  bodyText: { flex: 1, color: 'rgba(251,246,240,0.92)', fontSize: 14.5, lineHeight: 21 },
  cta: {
    minHeight: 48,
    borderRadius: 999,
    backgroundColor: 'rgba(21,16,31,0.62)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaText: { color: '#fbf6f0', fontSize: 15, fontWeight: '500' },
});
