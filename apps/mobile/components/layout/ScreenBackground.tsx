import React from 'react';
import { StyleSheet, View, type ViewStyle, useWindowDimensions } from 'react-native';

import { AmbientBackground } from '../ambient/AmbientBackground';

/**
 * B3 (independent review of PR #332): every screen renders
 * `AmbientBackground` — no screen hard-codes `backgroundColor:'#1f1731'`
 * (the gradient's own last stop) as a stand-in. `AppShell` renders this
 * once for the tabs group; every screen outside it (Welcome through
 * Insight — none of them are tabs) wraps itself in this instead of
 * repeating the width/height/Canvas boilerplate six times over.
 */
export function ScreenBackground({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const { width, height } = useWindowDimensions();
  return (
    <View style={[styles.root, style]}>
      <AmbientBackground width={width} height={height} />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, overflow: 'hidden' },
});
