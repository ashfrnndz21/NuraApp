import React, { useMemo } from 'react';
import { StyleSheet, Text, type StyleProp, type TextStyle } from 'react-native';

export interface EditorialHeadlineProps {
  /** One `*accent*` word or phrase, rendered in italic serif — e.g. "Four numbers to raise with your *doctor.*" */
  text: string;
  size?: number;
  /** Merged onto the outer `Text` — e.g. `{ flex: 1 }` beside an orb in a row (insight.tsx). */
  style?: StyleProp<TextStyle>;
}

/**
 * The large editorial headline (spec §4), one word emphasised in italic
 * serif (Instrument Serif — the reference's font). Plain Figtree-style
 * weight everywhere else.
 */
export function EditorialHeadline({ text, size = 33, style }: EditorialHeadlineProps) {
  const parts = useMemo(() => text.split(/\*(.+?)\*/g), [text]);

  return (
    <Text style={[styles.headline, { fontSize: size, lineHeight: size * 1.1 }, style]} accessibilityRole="header">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <Text key={i} style={[styles.accent, { fontSize: size * 1.12 }]}>
            {part}
          </Text>
        ) : (
          <Text key={i}>{part}</Text>
        )
      )}
    </Text>
  );
}

const styles = StyleSheet.create({
  headline: {
    color: '#fbf6f0',
    fontWeight: '300',
    letterSpacing: -0.4,
  },
  accent: {
    fontFamily: 'InstrumentSerif_400Regular_Italic',
    fontStyle: 'italic',
  },
});
