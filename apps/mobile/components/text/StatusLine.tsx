import React, { useEffect, useRef } from 'react';
import { StyleSheet, Text } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { statusIn, statusOut } from '../motion/motionTokens';
import { useReducedMotion } from '../motion/useReducedMotion';

export interface StatusLineProps {
  text: string | null;
  size?: number;
}

/**
 * "Never 'Loading…'" (spec §21): one line that changes in place, softly
 * — never a stack of lines. Intelligent phrasing lives with the caller
 * (e.g. the composer's `stage` copy); this component only handles the
 * in-place transition.
 */
export function StatusLine({ text, size = 18.5 }: StatusLineProps) {
  const reducedMotion = useReducedMotion();
  const opacity = useSharedValue(0);
  const lastText = useRef<string | null>(null);

  useEffect(() => {
    if (text === lastText.current) return;
    lastText.current = text;
    if (reducedMotion) {
      opacity.value = text ? 1 : 0;
      return;
    }
    if (text) {
      opacity.value = 0;
      opacity.value = withTiming(1, { duration: statusIn });
    } else {
      opacity.value = withTiming(0, { duration: statusOut });
    }
  }, [text, reducedMotion, opacity]);

  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));

  if (!text) return null;

  return (
    <Animated.View style={style}>
      <Text style={[styles.status, { fontSize: size }]} testID="status-line">
        {text}…
      </Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  status: {
    color: 'rgba(251,246,240,0.72)',
    fontWeight: '300',
  },
});
