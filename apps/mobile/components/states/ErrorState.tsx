import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { NuraCard } from '../cards/NuraCard';
import { AIOrb } from '../ambient/IntelligenceOrb';

export interface ErrorStateProps {
  /** Card title (`.card h3` — e.g. "Your clinic records"). */
  title: string;
  /**
   * The plain-words refusal sentence, from the backend
   * (`app.safety.plain_words` — never an HTTP code, never engine jargon).
   */
  why: string;
  ctaLabel: string;
  onPress: () => void;
  testID?: string;
}

/**
 * DESIGN_SYSTEM.md §14: `data-variant="alert" data-tier="primary"`, an
 * error-state orb, title + why + light-filled CTA ("Try again"). The
 * orb's own error glow carries the calm-not-alarming read — no extra
 * motion, no red flashing.
 */
export function ErrorState({ title, why, ctaLabel, onPress, testID }: ErrorStateProps) {
  return (
    <NuraCard variant="alert" tier="primary" testID={testID} accessibilityLabel={`${title}. ${why}`}>
      <View style={styles.header}>
        <AIOrb size="sm" stateOverride="error" />
        <Text style={styles.title}>{title}</Text>
      </View>
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
  header: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontSize: 19, fontWeight: '300', lineHeight: 24.7, color: '#fbf6f0', flexShrink: 1 },
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
