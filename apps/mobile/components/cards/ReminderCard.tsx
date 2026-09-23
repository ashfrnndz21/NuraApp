import React, { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withDelay, withTiming } from 'react-native-reanimated';

import { cardEnter, pressIn, scalePress } from '../motion/motionTokens';
import { springs } from '../motion/springs';
import { useReducedMotion } from '../motion/useReducedMotion';

export interface ReminderCardProps {
  label: string;
  done?: boolean;
  onToggle?: () => void;
  enterIndex?: number;
  staggerMs?: number;
}

/**
 * A single-line reminder (spec §5, the `.line` pattern): one thing, a
 * tappable check at the end. Same press/enter motion as every card.
 */
export function ReminderCard({ label, done, onToggle, enterIndex = 0, staggerMs = 0 }: ReminderCardProps) {
  const reducedMotion = useReducedMotion();
  const opacity = useSharedValue(reducedMotion ? 1 : 0);
  const translateY = useSharedValue(reducedMotion ? 0 : 12);
  const scale = useSharedValue(1);

  useEffect(() => {
    if (reducedMotion) {
      opacity.value = 1;
      translateY.value = 0;
      return;
    }
    const delay = enterIndex * staggerMs;
    opacity.value = withDelay(delay, withTiming(1, { duration: cardEnter }));
    translateY.value = withDelay(delay, withTiming(0, { duration: cardEnter }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }, { scale: scale.value }],
  }));

  return (
    <Animated.View style={style}>
      <Pressable
        style={styles.line}
        onPress={onToggle}
        onPressIn={() => {
          scale.value = withTiming(scalePress, { duration: pressIn });
          if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        }}
        onPressOut={() => {
          scale.value = withTiming(1, springs.bouncy);
        }}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ checked: !!done }}
        testID="reminder-card"
      >
        <Text style={styles.label}>{label}</Text>
        <View style={[styles.plus, done && styles.plusDone]}>
          <Text style={styles.check}>{done ? '✓' : ''}</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  line: {
    minHeight: 60,
    borderRadius: 24,
    paddingHorizontal: 12,
    paddingLeft: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
  },
  label: { flex: 1, color: '#fbf6f0', fontSize: 16.5, fontWeight: '300' },
  plus: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plusDone: { backgroundColor: '#a9d3ae' },
  check: { color: '#16301c', fontSize: 16, fontWeight: '700' },
});
