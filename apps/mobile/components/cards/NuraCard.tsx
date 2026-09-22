import React, { useEffect } from 'react';
import { Platform, Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { BlurView } from 'expo-blur';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withTiming,
} from 'react-native-reanimated';

import { cardEnter, pressIn, pressOut, scalePress } from '../motion/motionTokens';
import { springs } from '../motion/springs';
import { useReducedMotion } from '../motion/useReducedMotion';

export type CardVariant =
  | 'insight'
  | 'reminder'
  | 'media'
  | 'metric'
  | 'recommendation'
  | 'document'
  | 'ai-summary'
  | 'action'
  | 'alert';

export type CardTier = 'primary' | 'secondary' | 'tertiary';

const ACCENT: Record<CardVariant, string> = {
  insight: '#c9a9e8',
  reminder: '#f3b562',
  media: '#9fd0ff',
  metric: '#a9d3ae',
  recommendation: '#e7b48f',
  document: '#fbe3cf',
  'ai-summary': '#c9a9e8',
  action: '#a9d3ae',
  alert: '#f3b562',
};

const RADIUS: Record<CardTier, number> = { primary: 28, secondary: 22, tertiary: 16 };
const PADDING: Record<CardTier, number> = { primary: 18, secondary: 14, tertiary: 4 };

export interface NuraCardProps {
  variant: CardVariant;
  tier?: CardTier;
  /** Index in a staggered list — multiplied by `staggerMs` for the entrance delay. */
  enterIndex?: number;
  staggerMs?: number;
  onPress?: () => void;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  children: React.ReactNode;
  testID?: string;
  accessibilityLabel?: string;
}

/**
 * One reusable card (spec §5): variants × three tiers, translucent glass
 * surface, large radius. Press: scale .985 / 100 ms + 4% brighter +
 * haptic, spring release (spec §7). Entrance: fade 0→1 + 12px rise on
 * `card.enter`, staggered by `enterIndex * staggerMs`.
 */
export function NuraCard({
  variant,
  tier = 'secondary',
  enterIndex = 0,
  staggerMs = 0,
  onPress,
  disabled,
  style,
  children,
  testID,
  accessibilityLabel,
}: NuraCardProps) {
  const reducedMotion = useReducedMotion();
  const opacity = useSharedValue(reducedMotion ? 1 : 0);
  const translateY = useSharedValue(reducedMotion ? 0 : 12);
  const scale = useSharedValue(1);
  const brighten = useSharedValue(0);

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

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }, { scale: scale.value }],
  }));

  const brightenStyle = useAnimatedStyle(() => ({ opacity: brighten.value }));

  const handlePressIn = () => {
    if (!onPress) return;
    scale.value = withTiming(scalePress, { duration: pressIn });
    brighten.value = withTiming(0.04, { duration: pressIn });
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }
  };

  const handlePressOut = () => {
    if (!onPress) return;
    scale.value = withTiming(1, springs.bouncy);
    brighten.value = withTiming(0, { duration: pressOut });
  };

  const tierRadius = RADIUS[tier];
  const tierPadding = PADDING[tier];
  const isTertiary = tier === 'tertiary';

  const inner = (
    <Animated.View
      style={[
        styles.base,
        {
          borderRadius: tierRadius,
          padding: tierPadding,
          backgroundColor: isTertiary ? 'transparent' : 'rgba(255,255,255,0.08)',
          borderWidth: isTertiary ? 0 : 1,
          borderColor: variant === 'alert' ? 'rgba(243,181,98,0.55)' : 'rgba(255,255,255,0.16)',
        },
        animatedStyle,
        style,
      ]}
      testID={testID}
      accessibilityLabel={accessibilityLabel}
    >
      {!isTertiary && Platform.OS !== 'web' ? (
        <BlurView intensity={22} tint="dark" style={StyleSheet.absoluteFill} pointerEvents="none" />
      ) : null}
      <View style={{ gap: isTertiary ? 6 : tier === 'secondary' ? 10 : 12 }}>{children}</View>
      <Animated.View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { borderRadius: tierRadius, backgroundColor: '#ffffff' }, brightenStyle]}
      />
    </Animated.View>
  );

  if (!onPress) return inner;

  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
    >
      {inner}
    </Pressable>
  );
}

export function CardAccentDot({ variant }: { variant: CardVariant }) {
  return <View style={[styles.inlineDot, { backgroundColor: ACCENT[variant] }]} />;
}

const styles = StyleSheet.create({
  base: {
    overflow: 'hidden',
    position: 'relative',
  },
  inlineDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
});
