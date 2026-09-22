import React, { useEffect } from 'react';
import { StyleSheet } from 'react-native';
import {
  Blur,
  Canvas,
  Circle,
  Group,
  LinearGradient,
  Rect,
  RadialGradient,
  vec,
} from '@shopify/react-native-skia';
import { useDerivedValue, useSharedValue, withTiming, type SharedValue } from 'react-native-reanimated';

import type { AIStateName } from '../ai/AIState';
import { useAIStateName } from '../ai/AIState';
import { phoneTokens } from '../motion/motionTokens';
import { timing } from '../motion/springs';
import { useReducedMotion } from '../motion/useReducedMotion';

const BRIGHTNESS_BY_STATE: Record<AIStateName, number> = {
  idle: 0,
  listening: 0.14,
  thinking: 0.22,
  responding: 0.28,
  error: -0.08,
};

export interface AmbientBackgroundProps {
  width: number;
  height: number;
  /** Reanimated shared value driven by the screen's own scroll handler. */
  scrollY?: SharedValue<number>;
}

/**
 * The dusk gradient + two radial "atmosphere" layers behind Home (spec
 * §2, blueprint `.atmos i.a` / `.atmos i.b`). Translated by scroll,
 * brightened slightly by AIState — never by a timer of its own.
 */
export function AmbientBackground({ width, height, scrollY }: AmbientBackgroundProps) {
  const aiState = useAIStateName();
  const reducedMotion = useReducedMotion();
  const brightness = useSharedValue(0);

  useEffect(() => {
    const target = BRIGHTNESS_BY_STATE[aiState];
    brightness.value = reducedMotion ? target : withTiming(target, timing.standard());
  }, [aiState, reducedMotion, brightness]);

  const fallbackScroll = useSharedValue(0);
  const scroll = scrollY ?? fallbackScroll;

  const layerAOpacity = useDerivedValue(() => phoneTokens.atmosLayerA.opacity + brightness.value);
  const layerBOpacity = useDerivedValue(() => phoneTokens.atmosLayerB.opacity + brightness.value * 0.8);
  const layerATranslate = useDerivedValue(() => (reducedMotion ? 0 : -scroll.value * 0.12));
  const layerBTranslate = useDerivedValue(() => (reducedMotion ? 0 : -scroll.value * 0.06));

  const aCenter = vec(width * 0.62, height * -0.05);
  const bCenter = vec(width * 0.05, height * 0.28);
  const aR = width * 0.55;
  const bR = width * 0.58;

  return (
    <Canvas style={StyleSheet.absoluteFill} pointerEvents="none">
      <Rect x={0} y={0} width={width} height={height}>
        <LinearGradient
          start={vec(0, 0)}
          end={vec(0, height)}
          colors={[...phoneTokens.atmosGradient]}
        />
      </Rect>
      <Group transform={useDerivedValue(() => [{ translateY: layerATranslate.value }])} opacity={layerAOpacity}>
        <Circle c={aCenter} r={aR} color={phoneTokens.atmosLayerA.color}>
          <RadialGradient
            c={aCenter}
            r={aR}
            colors={[phoneTokens.atmosLayerA.color, `${phoneTokens.atmosLayerA.color}00`]}
          />
        </Circle>
        <Blur blur={38} />
      </Group>
      <Group transform={useDerivedValue(() => [{ translateY: layerBTranslate.value }])} opacity={layerBOpacity}>
        <Circle c={bCenter} r={bR} color={phoneTokens.atmosLayerB.color}>
          <RadialGradient
            c={bCenter}
            r={bR}
            colors={[phoneTokens.atmosLayerB.color, `${phoneTokens.atmosLayerB.color}00`]}
          />
        </Circle>
        <Blur blur={44} />
      </Group>
    </Canvas>
  );
}
