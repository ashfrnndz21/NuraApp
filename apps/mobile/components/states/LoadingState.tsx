import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming, withRepeat } from 'react-native-reanimated';

import { NuraCard } from '../cards/NuraCard';
import { AIOrb } from '../ambient/IntelligenceOrb';
import { StatusLine } from '../text/StatusLine';
import { sweep } from '../../design/motion';
import { useReducedMotion } from '../motion/useReducedMotion';

export interface LoadingStateProps {
  /**
   * The current status line — e.g. a `TOOL_CALL_START.stage` word from
   * the run event stream (spec: "never a fake progress bar", C2). This
   * component owns no timer of its own; the caller re-renders it with a
   * new `line` as real events arrive, and the cross-fade below is driven
   * by that prop change, not a schedule.
   */
  line: string;
  testID?: string;
}

/**
 * DESIGN_SYSTEM.md §14: `data-variant="ai-summary" data-tier="secondary"`,
 * a thinking orb, one status line that swaps in place (never a stack),
 * two shimmer bars (82%/64% width). The shimmer's continuous sweep is
 * decorative motion, not a substitute for real progress — the line text
 * itself only ever changes when the caller passes a new one.
 */
export function LoadingState({ line, testID }: LoadingStateProps) {
  const reducedMotion = useReducedMotion();
  const shimmer = useSharedValue(0);

  useEffect(() => {
    if (reducedMotion) return;
    // Continuous ping-pong (reverse:true) — a sweep, not a stepped reset — so
    // no second withTiming(0, …) leg is needed to snap back to the start.
    shimmer.value = withRepeat(withTiming(1, { duration: sweep }), -1, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  const shimmerStyle = useAnimatedStyle(() => ({
    opacity: reducedMotion ? 0.55 : 0.35 + shimmer.value * 0.25,
  }));

  return (
    <NuraCard variant="ai-summary" tier="secondary" testID={testID} accessibilityLabel={line}>
      <View style={styles.header}>
        <AIOrb size="sm" stateOverride="thinking" />
        <StatusLine text={line} />
      </View>
      <Animated.View style={[styles.shim, { width: '82%' }, shimmerStyle]} />
      <Animated.View style={[styles.shim, { width: '64%' }, shimmerStyle]} />
    </NuraCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  shim: {
    height: 12,
    borderRadius: 6,
    backgroundColor: 'rgba(255,255,255,0.14)',
    marginTop: 8,
  },
});
