import React from 'react';
import { Tabs } from 'expo-router';

import { BottomNavigation } from '../nav/BottomNavigation';

/**
 * ADR 0020's `AppShell` decision: the `Tabs` root plus its own
 * `BottomNavigation`, named and extracted out of `app/(tabs)/_layout.tsx`
 * (which now only renders this). One shell, five fixed tabs — no
 * variants or props today (ADR 0020's own `AppShell` table).
 */
export function AppShell() {
  return (
    <Tabs tabBar={() => <BottomNavigation />} screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="home" />
      <Tabs.Screen name="health" />
      <Tabs.Screen name="connect" />
      <Tabs.Screen name="services" />
      <Tabs.Screen name="profile" />
    </Tabs>
  );
}
