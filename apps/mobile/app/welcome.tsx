import React, { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import Animated, { useAnimatedStyle, useSharedValue, withDelay, withTiming } from 'react-native-reanimated';

import { AIOrb } from '../components/ambient/IntelligenceOrb';
import { ScreenBackground } from '../components/layout/ScreenBackground';
import { EditorialHeadline } from '../components/text/EditorialHeadline';
import { cardEnter, staggerStep } from '../design/motion';
import { phoneTokens, semanticColors } from '../design/colors';
import * as typography from '../design/typography';
import { useReducedMotion } from '../components/motion/useReducedMotion';

/**
 * Scene 1 (v2 frame 01): orb-first Welcome — the orb, the headline with
 * one *accent* word in italic serif, a one-line subtitle, one CTA. No
 * form, no chrome, nothing to decide yet — the orb is the whole page.
 */
export default function Welcome() {
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const orbOpacity = useSharedValue(reducedMotion ? 1 : 0);
  const textOpacity = useSharedValue(reducedMotion ? 1 : 0);
  const ctaOpacity = useSharedValue(reducedMotion ? 1 : 0);

  useEffect(() => {
    if (reducedMotion) return;
    orbOpacity.value = withTiming(1, { duration: cardEnter });
    textOpacity.value = withDelay(staggerStep, withTiming(1, { duration: cardEnter }));
    ctaOpacity.value = withDelay(staggerStep * 2, withTiming(1, { duration: cardEnter }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  const orbStyle = useAnimatedStyle(() => ({ opacity: orbOpacity.value }));
  const textStyle = useAnimatedStyle(() => ({ opacity: textOpacity.value }));
  const ctaStyle = useAnimatedStyle(() => ({ opacity: ctaOpacity.value }));

  return (
    <ScreenBackground style={styles.screen}>
      <View style={styles.center}>
        <Animated.View style={orbStyle}>
          <AIOrb size="lg" stateOverride="idle" />
        </Animated.View>
        <Animated.View style={[styles.textBlock, textStyle]}>
          <EditorialHeadline text="Your health, in *plain* words." size={33} />
          <Text style={styles.subtitle}>Show me your papers. Ask me anything about them.</Text>
        </Animated.View>
      </View>
      <Animated.View style={ctaStyle}>
        <Pressable
          style={styles.cta}
          onPress={() => router.push('/sign-in')}
          accessibilityRole="button"
          accessibilityLabel="Start"
          testID="welcome-start"
        >
          <Text style={styles.ctaText}>Start</Text>
        </Pressable>
      </Animated.View>
    </ScreenBackground>
  );
}

const styles = StyleSheet.create({
  screen: {
    paddingHorizontal: 20,
    paddingTop: 120,
    paddingBottom: 40,
    justifyContent: 'space-between',
  },
  center: { alignItems: 'center', gap: 24 },
  textBlock: { alignItems: 'center', gap: 12 },
  subtitle: {
    color: 'rgba(251,246,240,0.75)',
    fontSize: typography.fontSize[15.5],
    lineHeight: 21,
    textAlign: 'center',
    maxWidth: 280,
  },
  cta: {
    minHeight: 56,
    borderRadius: 999,
    backgroundColor: phoneTokens.c,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaText: { color: semanticColors.inkOnLight, fontWeight: '600', fontSize: typography.fontSize[17] },
});
