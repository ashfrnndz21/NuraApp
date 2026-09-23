import React, { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  Easing,
  cancelAnimation,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { mediaRun, pressOut } from '../motion/motionTokens';
import { radii } from '../../design/tokens';
import { NuraCard } from './NuraCard';

export type MediaState = 'idle' | 'loading' | 'playing' | 'paused' | 'complete';

export interface MediaCardProps {
  title: string;
  why: string;
  publisher: string;
  duration: string;
  enterIndex?: number;
  staggerMs?: number;
  onStateChange?: (state: MediaState) => void;
}

/**
 * Editorial media card (spec §13): why before what. State machine —
 * idle → loading → playing ⇄ paused → complete (mobile-architecture §3).
 *
 * Spike debt, named rather than silently carried (FIX BEFORE MERGE,
 * independent review of PR #332): "playing" here is a `setTimeout`
 * counting down `mediaRun`, not a real player — no golden-path screen
 * uses this component (there is no media/video feed item in this
 * checkpoint), so the fake progress it draws never reaches anyone. Kept
 * as spike-only scaffolding; replace the timer with a real player's own
 * progress event before any screen puts this on the golden path.
 */
export function MediaCard({ title, why, publisher, duration, enterIndex, staggerMs, onStateChange }: MediaCardProps) {
  const [state, setState] = useState<MediaState>('idle');
  const progress = useSharedValue(0);

  const setAndNotify = useCallback(
    (next: MediaState) => {
      setState(next);
      onStateChange?.(next);
    },
    [onStateChange]
  );

  const onPress = () => {
    if (state === 'idle') {
      setAndNotify('loading');
      setTimeout(() => {
        setAndNotify('playing');
        progress.value = withTiming(
          1,
          { duration: mediaRun * (1 - progress.value), easing: Easing.linear },
          (finished) => {
            if (finished) runOnJS(setAndNotify)('complete');
          }
        );
      }, pressOut);
      return;
    }
    if (state === 'playing') {
      cancelAnimation(progress);
      setAndNotify('paused');
      return;
    }
    if (state === 'paused') {
      setAndNotify('playing');
      progress.value = withTiming(
        1,
        { duration: mediaRun * (1 - progress.value), easing: Easing.linear },
        (finished) => {
          if (finished) runOnJS(setAndNotify)('complete');
        }
      );
      return;
    }
    if (state === 'complete') {
      progress.value = 0;
      setAndNotify('idle');
    }
  };

  const barStyle = useAnimatedStyle(() => ({ width: `${progress.value * 100}%` }));

  const icon = state === 'loading' ? '···' : state === 'playing' ? '❚❚' : state === 'complete' ? '↺' : '▶';

  return (
    <NuraCard variant="media" tier="secondary" enterIndex={enterIndex} staggerMs={staggerMs} testID="media-card">
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`${title}. ${state}`}
        testID="media-card-play"
      >
        <View style={styles.poster}>
          <LinearGradient
            colors={['#9fd0ff', '#6f4fc4', '#1f1731']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={StyleSheet.absoluteFill}
          />
          <Text style={styles.posterTitle}>{title}</Text>
          <View style={styles.playButton}>
            <Text style={styles.playIcon}>{icon}</Text>
          </View>
          {(state === 'playing' || state === 'paused') && (
            <View style={styles.progressTrack} testID="media-progress">
              <Animated.View style={[styles.progressFill, barStyle]} />
            </View>
          )}
        </View>
      </Pressable>
      <Text style={styles.why}>{why}</Text>
      <Text style={styles.meta}>
        {publisher} · {duration}
      </Text>
    </NuraCard>
  );
}

const styles = StyleSheet.create({
  poster: {
    height: 150,
    borderRadius: radii.mediaPoster,
    overflow: 'hidden',
    justifyContent: 'space-between',
    padding: 14,
  },
  posterTitle: { color: '#fbf6f0', fontSize: 16, fontWeight: '600', maxWidth: '80%' },
  playButton: {
    alignSelf: 'flex-end',
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: 'rgba(255,255,255,0.22)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  playIcon: { color: '#fbf6f0', fontSize: 15 },
  progressTrack: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  progressFill: { height: 3, backgroundColor: '#fbf6f0' },
  why: { color: 'rgba(251,246,240,0.92)', fontSize: 14, paddingHorizontal: 4 },
  meta: { color: 'rgba(251,246,240,0.6)', fontSize: 12, paddingHorizontal: 4, paddingBottom: 2 },
});
