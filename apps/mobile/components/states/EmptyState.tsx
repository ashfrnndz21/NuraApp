import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';

import { NuraCard } from '../cards/NuraCard';

export interface EmptyStateProps {
  /** Card title (`.card h3` — e.g. "Blood pressure"). */
  title: string;
  /** Why line — the honest, specific "nothing here yet" sentence (spec §22: why → what → next). */
  why: string;
  ctaLabel: string;
  onPress: () => void;
  testID?: string;
}

/**
 * DESIGN_SYSTEM.md §14: `data-variant="metric" data-tier="primary"`, one
 * title line, one why line, one light-filled CTA. No motion beyond the
 * card's own entrance — this is the one shared shape for "nothing here
 * yet", never per-screen copy (A-167).
 */
export function EmptyState({ title, why, ctaLabel, onPress, testID }: EmptyStateProps) {
  return (
    <NuraCard variant="metric" tier="primary" testID={testID} accessibilityLabel={`${title}. ${why}`}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.why}>{why}</Text>
      <Pressable
        onPress={onPress}
        style={styles.cta}
        accessibilityRole="button"
        accessibilityLabel={ctaLabel}
      >
        <Text style={styles.ctaText}>{ctaLabel}</Text>
      </Pressable>
    </NuraCard>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 19, fontWeight: '300', lineHeight: 24.7, color: '#fbf6f0' },
  why: { opacity: 0.8, color: '#fbf6f0', marginTop: 4 },
  cta: {
    marginTop: 10,
    minHeight: 48,
    borderRadius: 999,
    backgroundColor: '#fbf6f0',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  ctaText: { color: '#2b2140', fontWeight: '600', fontSize: 15 },
});
