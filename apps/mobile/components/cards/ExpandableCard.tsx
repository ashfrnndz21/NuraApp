import React, { useEffect, useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

import { alarmReveal, chartDraw, motionStandard, pressIn, scalePress, statusOut } from '../motion/motionTokens';
import { springs } from '../motion/springs';
import { useReducedMotion } from '../motion/useReducedMotion';
import { NuraCard } from './NuraCard';
import { BPChart } from './BPChart';

export type ExpandableCardState = 'collapsed' | 'pressed' | 'expanding' | 'expanded' | 'interactive' | 'dismissed';

const BP_DAYS = [
  { d: 'Mon', sys: '128', dia: '78' },
  { d: 'Tue', sys: '131', dia: '80' },
  { d: 'Wed', sys: '139', dia: '86' },
  { d: 'Thu', sys: '142', dia: '88' },
  { d: 'Fri', sys: '145', dia: '90' },
  { d: 'Sat', sys: '144', dia: '89' },
  { d: 'Sun', sys: '148', dia: '92' },
];
const BP_POINTS: Array<[number, number]> = [
  [8, 62],
  [59, 58],
  [110, 44],
  [161, 38],
  [212, 30],
  [263, 33],
  [312, 20],
];
const CHART_W = 320;
const CHART_H = 74;

const HINTS = [
  'Tap to see the week',
  'Tap for the daily values',
  'Tap for what changed',
  'Tap for what it connects to',
  'Tap for what you can do',
  'Tap to close',
];

export interface ExpandableCardProps {
  bpExplain: string;
  possessive: 'your' | "Pa's" | string;
  onKeepForVisit?: () => void;
  onStateChange?: (state: ExpandableCardState, step: number) => void;
}

/**
 * The progressive-disclosure blood-pressure card (spec §11, blueprint
 * scene 30): the same object growing in place through collapsed →
 * pressed → expanding → expanded → interactive → dismissed, five taps
 * of content then a sixth that closes it.
 */
export function ExpandableCard({ bpExplain, possessive, onKeepForVisit, onStateChange }: ExpandableCardProps) {
  const [step, setStep] = useState(0);
  const [state, setState] = useState<ExpandableCardState>('collapsed');
  const [cardWidth, setCardWidth] = useState(CHART_W);
  const reducedMotion = useReducedMotion();
  const pressScale = useSharedValue(1);
  const chartProgress = useSharedValue(0);
  const contentOpacity = useSharedValue(0);

  useEffect(() => {
    onStateChange?.(state, step);
  }, [state, step, onStateChange]);

  const advance = () => {
    const next = step >= 5 ? 0 : step + 1;
    if (next === 0) {
      setState('dismissed');
      contentOpacity.value = reducedMotion ? 0 : withTiming(0, { duration: statusOut });
      setTimeout(() => setState('collapsed'), reducedMotion ? 0 : statusOut);
    } else if (next === 1) {
      setState('expanding');
      contentOpacity.value = reducedMotion ? 1 : withTiming(1, { duration: chartDraw });
      chartProgress.value = 0;
      chartProgress.value = reducedMotion ? 1 : withDelay(alarmReveal, withTiming(1, { duration: chartDraw }));
      setTimeout(() => setState('expanded'), reducedMotion ? 0 : chartDraw);
    } else {
      setState('interactive');
      contentOpacity.value = reducedMotion ? 1 : withTiming(1, { duration: motionStandard });
    }
    setStep(next);
  };

  const handlePressIn = () => {
    setState((s) => (s === 'collapsed' || s === 'expanded' || s === 'interactive' ? 'pressed' : s));
    pressScale.value = withTiming(scalePress, { duration: pressIn });
    if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  };
  const handlePressOut = () => {
    pressScale.value = withTiming(1, springs.bouncy);
  };

  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: pressScale.value }] }));
  const contentStyle = useAnimatedStyle(() => ({ opacity: contentOpacity.value }));

  const onChartLayout = (e: LayoutChangeEvent) => setCardWidth(e.nativeEvent.layout.width);

  return (
    <Animated.View style={pressStyle} testID="expandable-card" accessibilityValue={{ text: state }}>
      <NuraCard variant="metric" tier="primary" testID="expandable-card-surface">
        <Pressable
          onPress={advance}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          accessibilityRole="button"
          accessibilityLabel={`Blood pressure, ${HINTS[step]}`}
          testID="expandable-card-trigger"
        >
          <View style={styles.headRow}>
            <Text style={styles.title}>Blood pressure</Text>
            <View style={styles.seg}>
              <Text style={styles.segActive}>Week</Text>
              <Text style={styles.segInactive}>Month</Text>
            </View>
          </View>
          <View style={styles.valueRow}>
            <Text style={styles.value}>
              148<Text style={styles.valueUnit}> over 92 today</Text>
            </Text>
            <View style={styles.flag}>
              <Text style={styles.flagText}>Above {possessive} usual</Text>
            </View>
          </View>
          <Text style={styles.hint}>▾ {HINTS[step]}</Text>
        </Pressable>

        {step >= 1 && (
          <Animated.View style={contentStyle} onLayout={onChartLayout}>
            <BPChart points={BP_POINTS} width={cardWidth} height={CHART_H} progress={chartProgress} />
            <Text style={styles.note}>
              Your own usual band, from your own mornings. Nura never compares you with other people.
            </Text>
          </Animated.View>
        )}

        {step >= 2 && (
          <View style={styles.daysRow}>
            {BP_DAYS.map((d, i) => (
              <View key={d.d} style={[styles.dayCol, i === BP_DAYS.length - 1 && styles.dayColOn]}>
                <Text style={styles.daySys}>{d.sys}</Text>
                <Text style={styles.dayDia}>{d.dia}</Text>
                <Text style={styles.dayLabel}>{d.d}</Text>
              </View>
            ))}
          </View>
        )}

        {step >= 3 && (
          <View style={styles.tertiary}>
            <Text style={styles.tertiaryTitle}>What changed</Text>
            <Text style={styles.tertiaryBody}>{bpExplain}</Text>
          </View>
        )}

        {step >= 4 && (
          <View style={styles.rows}>
            <View style={styles.rowItem}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>Blood pressure tablet</Text>
                <Text style={styles.rowSub}>Went from 5 mg to 10 mg on 9 September</Text>
              </View>
              <Text style={styles.flagQ}>Changed</Text>
            </View>
            <View style={styles.rowItem}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>Blood test</Text>
                <Text style={styles.rowSub}>12 September · 5 results · 4 outside</Text>
              </View>
              <Text style={styles.flagHi}>Look</Text>
            </View>
          </View>
        )}

        {step >= 5 && (
          <View style={styles.tertiary}>
            <Text style={styles.tertiaryTitle}>What you can do</Text>
            <Pressable
              style={styles.actionBtn}
              onPress={(e) => {
                e.stopPropagation?.();
                onKeepForVisit?.();
              }}
              accessibilityRole="button"
              testID="expandable-card-action"
            >
              <Text style={styles.actionBtnText}>Keep this for Dr Lim on 25 September</Text>
            </Pressable>
          </View>
        )}
      </NuraCard>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  headRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: '#fbf6f0', fontSize: 18, fontWeight: '400' },
  seg: { flexDirection: 'row', gap: 4 },
  segActive: {
    color: '#2b2140',
    backgroundColor: '#fbf6f0',
    fontSize: 12,
    fontWeight: '600',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 999,
    overflow: 'hidden',
  },
  segInactive: { color: 'rgba(251,246,240,0.7)', fontSize: 12, paddingVertical: 6, paddingHorizontal: 8 },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8 },
  value: { color: '#fbf6f0', fontSize: 30, fontWeight: '600' },
  valueUnit: { fontSize: 13, fontWeight: '400', opacity: 0.75 },
  flag: { marginLeft: 'auto', backgroundColor: '#f3b562', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 },
  flagText: { color: '#231a12', fontSize: 11.5, fontWeight: '600' },
  hint: { color: 'rgba(251,246,240,0.65)', fontSize: 13, marginTop: 4 },
  note: { color: 'rgba(251,246,240,0.75)', fontSize: 12.5, marginTop: 6, lineHeight: 17 },
  daysRow: { flexDirection: 'row', justifyContent: 'space-between' },
  dayCol: { alignItems: 'center', gap: 2, opacity: 0.7 },
  dayColOn: { opacity: 1 },
  daySys: { color: '#fbf6f0', fontSize: 15, fontWeight: '500' },
  dayDia: { color: 'rgba(251,246,240,0.7)', fontSize: 11.5 },
  dayLabel: { color: 'rgba(251,246,240,0.6)', fontSize: 11 },
  tertiary: { gap: 6 },
  tertiaryTitle: { color: 'rgba(251,246,240,0.82)', fontSize: 15, fontWeight: '500' },
  tertiaryBody: { color: '#fbf6f0', fontSize: 15.5, fontWeight: '300', lineHeight: 21 },
  rows: { gap: 8 },
  rowItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 18,
    padding: 11,
    backgroundColor: 'rgba(255,255,255,0.06)',
  },
  rowTitle: { color: '#fbf6f0', fontSize: 15, fontWeight: '500' },
  rowSub: { color: 'rgba(251,246,240,0.74)', fontSize: 11.5 },
  flagQ: { color: '#f7cf94', fontSize: 11.5, fontWeight: '600' },
  flagHi: { color: '#231a12', backgroundColor: '#f3b562', fontSize: 11.5, fontWeight: '600', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999 },
  actionBtn: {
    minHeight: 48,
    borderRadius: 999,
    backgroundColor: '#fbf6f0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBtnText: { color: '#2b2140', fontSize: 15, fontWeight: '600' },
});
