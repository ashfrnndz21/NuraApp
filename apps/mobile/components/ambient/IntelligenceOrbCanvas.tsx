import React, { useEffect, useMemo } from 'react';
import { View } from 'react-native';
import { Blur, Canvas, Circle, Group, SweepGradient, vec } from '@shopify/react-native-skia';
import {
  Easing,
  cancelAnimation,
  useDerivedValue,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { useAIState, type AIStateName } from '../ai/AIState';
import { breathe, orbIdle, orbListening, orbResponding, orbThinking } from '../motion/motionTokens';
import { useReducedMotion } from '../motion/useReducedMotion';

const GRADIENT = ['#fbe3cf', '#c9a9e8', '#6f4fc4', '#f0b48f', '#9fd0ff', '#fbe3cf'];
const GRADIENT_ERROR = ['#cfc9d6', '#b9b3c2', '#9d97a8', '#c2bcc9', '#aba5b6', '#cfc9d6'];

const SPIN_DURATION: Record<AIStateName, number> = {
  idle: orbIdle,
  listening: orbListening,
  thinking: orbThinking,
  responding: orbResponding,
  error: orbIdle,
};

const HALO_ANIMATION: Record<AIStateName, 'halo' | 'pulse' | 'wave' | 'none'> = {
  idle: 'none',
  listening: 'halo',
  thinking: 'pulse',
  responding: 'wave',
  error: 'none',
};

export type OrbSize = 'sm' | 'md' | 'lg';
const SIZE_PX: Record<OrbSize, number> = { sm: 36, md: 74, lg: 128 };

export interface IntelligenceOrbProps {
  size?: OrbSize;
  /** Override the store's state — used by the orb-states showcase / tests. Normally omitted. */
  stateOverride?: AIStateName;
}

/**
 * The five-state orb (spec §8). A Skia gradient sphere; state comes only
 * from `AIState` (the store), never from a timer inside this component —
 * the sweep keeps spinning while idle, but which *state* it is in is
 * always someone else's decision.
 */
export function IntelligenceOrb({ size = 'md', stateOverride }: IntelligenceOrbProps) {
  const storeState = useAIState((s) => s.state);
  const state = stateOverride ?? storeState;
  const reducedMotion = useReducedMotion();
  const px = SIZE_PX[size];
  const r = px / 2;

  const rotation = useSharedValue(0);
  const halo = useSharedValue(0);
  const breath = useSharedValue(1);

  useEffect(() => {
    cancelAnimation(rotation);
    if (reducedMotion) {
      rotation.value = 0;
    } else {
      rotation.value = withRepeat(withTiming(360, { duration: SPIN_DURATION[state], easing: Easing.linear }), -1);
    }
  }, [state, reducedMotion, rotation]);

  useEffect(() => {
    cancelAnimation(halo);
    const anim = HALO_ANIMATION[state];
    if (reducedMotion || anim === 'none') {
      halo.value = state === 'error' ? 0.4 : 0;
      return;
    }
    const duration = SPIN_DURATION[state];
    if (anim === 'halo' || anim === 'wave') {
      halo.value = 0;
      halo.value = withRepeat(
        withSequence(
          withTiming(1, { duration: duration * 0.35, easing: Easing.out(Easing.ease) }),
          withTiming(0, { duration: duration * 0.65, easing: Easing.in(Easing.ease) })
        ),
        -1
      );
    } else {
      halo.value = withRepeat(
        withSequence(
          withTiming(1, { duration: duration / 2, easing: Easing.inOut(Easing.ease) }),
          withTiming(0, { duration: duration / 2, easing: Easing.inOut(Easing.ease) })
        ),
        -1
      );
    }
  }, [state, reducedMotion, halo]);

  useEffect(() => {
    cancelAnimation(breath);
    if (reducedMotion || state !== 'idle') {
      breath.value = 1;
      return;
    }
    breath.value = withRepeat(
      withSequence(
        withTiming(1.04, { duration: breathe / 2, easing: Easing.inOut(Easing.ease) }),
        withTiming(1, { duration: breathe / 2, easing: Easing.inOut(Easing.ease) })
      ),
      -1
    );
  }, [state, reducedMotion, breath]);

  const colors = useMemo(() => (state === 'error' ? GRADIENT_ERROR : GRADIENT), [state]);
  // B2 (independent review of PR #332): the glow circle (r×1.35, blurred by r×0.5) reaches
  // past this component's own px×px box — clipped by a Canvas the same px×px size as the
  // View wrapping it, which read on screen as a flat, square-edged disc rather than a soft
  // sphere. `CANVAS_PAD` grows the Canvas to 2× the orb's own box (this View's own layout
  // footprint is unchanged — the padding is absolutely positioned, so it never pushes
  // anything else around) and every drawn coordinate below is offset by it, so the glow's
  // own blur has room to fall off before it hits an edge.
  const CANVAS_PAD = r;
  const canvasSize = px + CANVAS_PAD * 2;
  const center = vec(r + CANVAS_PAD, r + CANVAS_PAD);

  const sweepTransform = useDerivedValue(() => [
    { translateX: r + CANVAS_PAD },
    { translateY: r + CANVAS_PAD },
    { rotate: (rotation.value * Math.PI) / 180 },
    { translateX: -(r + CANVAS_PAD) },
    { translateY: -(r + CANVAS_PAD) },
    { scale: state === 'idle' ? breath.value : 1 },
  ]);

  const haloOpacity = useDerivedValue(() => halo.value * (state === 'error' ? 0.4 : 0.7));
  const haloScale = useDerivedValue(() => 0.92 + halo.value * (HALO_ANIMATION[state] === 'pulse' ? 0.24 : 0.38));
  const haloTransform = useDerivedValue(() => [
    { translateX: r + CANVAS_PAD },
    { translateY: r + CANVAS_PAD },
    { scale: haloScale.value },
    { translateX: -(r + CANVAS_PAD) },
    { translateY: -(r + CANVAS_PAD) },
  ]);

  const glowOpacity = state === 'error' ? 0.18 : state === 'idle' ? 0.35 : 0.55;

  return (
    <View
      style={{ width: px, height: px, overflow: 'visible' }}
      accessible
      accessibilityRole="image"
      accessibilityLabel={`Nura, ${state}`}
    >
      <Canvas
        style={{
          position: 'absolute',
          left: -CANVAS_PAD,
          top: -CANVAS_PAD,
          width: canvasSize,
          height: canvasSize,
        }}
        pointerEvents="none"
      >
        <Group opacity={glowOpacity}>
          <Circle c={center} r={r * 1.35} color={colors[1]}>
            <Blur blur={r * 0.5} />
          </Circle>
        </Group>
        <Group transform={sweepTransform}>
          <Circle c={center} r={r}>
            <SweepGradient c={center} colors={colors} />
          </Circle>
        </Group>
        <Circle c={vec(r * 0.82 + CANVAS_PAD, r * 0.7 + CANVAS_PAD)} r={r * 0.32} color="white" opacity={0.5}>
          <Blur blur={r * 0.15} />
        </Circle>
        <Group opacity={haloOpacity} transform={haloTransform}>
          <Circle c={center} r={r} color="transparent" style="stroke" strokeWidth={1.4}>
            <SweepGradient c={center} colors={colors} />
          </Circle>
        </Group>
      </Canvas>
    </View>
  );
}
