import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Tabs, usePathname, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

const TAB_ITEMS = [
  { name: 'home', label: 'Home', icon: '⌂' },
  { name: 'health', label: 'Health', icon: '♡' },
  { name: 'connect', label: 'Connect', icon: '⚭' },
  { name: 'services', label: 'Services', icon: '▣' },
  { name: 'profile', label: 'Profile', icon: '◔' },
] as const;

/**
 * Minimal bottom navigation (spec §17): five quiet tabs, content is the
 * hero. A subtle, obvious active state — nothing louder.
 */
function BottomNavigation() {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 10) }]} testID="bottom-navigation">
      {TAB_ITEMS.map((tab) => {
        const active = pathname === `/${tab.name}` || (tab.name === 'home' && pathname === '/');
        return (
          <Pressable
            key={tab.name}
            style={styles.tab}
            onPress={() => router.navigate(`/${tab.name}` as never)}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={tab.label}
            testID={`tab-${tab.name}`}
          >
            <Text style={[styles.icon, active && styles.iconActive]}>{tab.icon}</Text>
            <Text style={[styles.label, active && styles.labelActive]}>{tab.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function TabsLayout() {
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

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 8,
    backgroundColor: '#1c1728',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  tab: { alignItems: 'center', gap: 3, minWidth: 62, minHeight: 46, paddingVertical: 2 },
  icon: { fontSize: 18, color: 'rgba(251,246,240,0.55)' },
  iconActive: { color: '#fbf6f0' },
  label: { fontSize: 11.5, color: 'rgba(251,246,240,0.55)' },
  labelActive: { color: '#fbf6f0', fontWeight: '600' },
});
