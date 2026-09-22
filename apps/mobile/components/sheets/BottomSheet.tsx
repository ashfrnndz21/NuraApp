import React, { useEffect } from 'react';
import { Dimensions, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { BlurView } from 'expo-blur';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { motionFast } from '../motion/motionTokens';
import { springs } from '../motion/springs';
import { useReducedMotion } from '../motion/useReducedMotion';

const DISMISS_DISTANCE = 110;
const DISMISS_VELOCITY = 800;

export interface BottomSheetProps {
  visible: boolean;
  onDismiss: () => void;
  title?: string;
  children: React.ReactNode;
  testID?: string;
}

/**
 * Bottom sheet over a dialog (spec §20): drag handle, spring entrance,
 * rounded top, dimmed + blurred backdrop, Gesture Handler drag with
 * velocity-aware dismissal. The blur is set once and never animated —
 * only the backdrop's opacity moves (blueprint scene 32).
 */
export function BottomSheet({ visible, onDismiss, title, children, testID }: BottomSheetProps) {
  const reducedMotion = useReducedMotion();
  const screenHeight = Dimensions.get('window').height;
  const translateY = useSharedValue(screenHeight);
  const backdropOpacity = useSharedValue(0);
  const dragStart = useSharedValue(0);

  useEffect(() => {
    if (visible) {
      backdropOpacity.value = reducedMotion ? 1 : withTiming(1, { duration: motionFast });
      translateY.value = reducedMotion ? 0 : withTiming(0, springs.standard as any);
    } else {
      backdropOpacity.value = reducedMotion ? 0 : withTiming(0, { duration: motionFast });
      translateY.value = reducedMotion ? screenHeight : withTiming(screenHeight, { duration: motionFast });
    }
  }, [visible, reducedMotion, backdropOpacity, translateY, screenHeight]);

  const dismiss = () => onDismiss();

  const pan = Gesture.Pan()
    .onStart(() => {
      dragStart.value = translateY.value;
    })
    .onUpdate((e) => {
      const next = dragStart.value + e.translationY;
      translateY.value = Math.max(0, next);
    })
    .onEnd((e) => {
      if (translateY.value > DISMISS_DISTANCE || e.velocityY > DISMISS_VELOCITY) {
        translateY.value = withTiming(screenHeight, { duration: motionFast }, (finished) => {
          if (finished) runOnJS(dismiss)();
        });
      } else {
        translateY.value = withTiming(0, springs.standard as any);
      }
    });

  const sheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: translateY.value }] }));
  const backdropStyle = useAnimatedStyle(() => ({ opacity: backdropOpacity.value }));

  if (!visible) return null;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none" testID={testID}>
      <Animated.View style={[StyleSheet.absoluteFill, backdropStyle]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={dismiss} accessibilityLabel="Dismiss" testID="sheet-backdrop">
          {Platform.OS === 'web' ? (
            <View style={[StyleSheet.absoluteFill, styles.webBackdrop]} />
          ) : (
            <BlurView intensity={28} tint="dark" style={StyleSheet.absoluteFill} />
          )}
        </Pressable>
      </Animated.View>
      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.sheet, sheetStyle]} testID="bottom-sheet" accessibilityViewIsModal>
          <View style={styles.handle} />
          {title ? <Text style={styles.title}>{title}</Text> : null}
          {children}
        </Animated.View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  webBackdrop: { backgroundColor: 'rgba(21,16,31,0.55)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(30,24,44,0.97)',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 34,
    gap: 14,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.28)',
    marginBottom: 4,
  },
  title: { color: '#fbf6f0', fontSize: 19, fontWeight: '600' },
});
