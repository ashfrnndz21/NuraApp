import 'react-native-gesture-handler';
import React, { useEffect, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useFonts, Figtree_300Light, Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold } from '@expo-google-fonts/figtree';
import { InstrumentSerif_400Regular_Italic } from '@expo-google-fonts/instrument-serif';

import { colorsDark } from '../design/colors';

/**
 * The web target has no native Skia — it renders through CanvasKit
 * (WASM), loaded once, asynchronously, before any `<Canvas>` mounts.
 * Native (Expo Go on the phone) needs none of this.
 */
function useSkiaWebReady() {
  const [ready, setReady] = useState(Platform.OS !== 'web');
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { LoadSkiaWeb } = require('@shopify/react-native-skia/lib/module/web');
    LoadSkiaWeb().then(() => {
      setReady(true);
      // Warm the lazy chunks that use Skia (AmbientBackground, IntelligenceOrb,
      // ExpandableCard's chart) now, off the interaction path, so the first tap
      // that needs one — e.g. ExpandableCard's first expand — isn't also
      // paying for the chunk's network fetch + Suspense resolution.
      import('../components/ambient/AmbientBackgroundCanvas').catch(() => {});
      import('../components/ambient/IntelligenceOrbCanvas').catch(() => {});
      import('../components/cards/BPChartCanvas').catch(() => {});
    });
  }, []);
  return ready;
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    Figtree_300Light,
    Figtree_400Regular,
    Figtree_500Medium,
    Figtree_600SemiBold,
    InstrumentSerif_400Regular_Italic,
  });
  const skiaReady = useSkiaWebReady();

  if (!fontsLoaded || !skiaReady) {
    return <View style={styles.loading} />;
  }

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="welcome" />
          <Stack.Screen name="sign-in" />
          <Stack.Screen name="who" />
          <Stack.Screen name="add-paper" />
          <Stack.Screen name="reading" />
          <Stack.Screen name="report" />
          <Stack.Screen name="insight" />
          <Stack.Screen name="ask" />
          <Stack.Screen name="not-well" />
          <Stack.Screen name="(tabs)" />
        </Stack>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colorsDark.paper },
  loading: { flex: 1, backgroundColor: colorsDark.paper },
});
