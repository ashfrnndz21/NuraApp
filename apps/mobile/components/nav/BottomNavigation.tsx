import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { phoneTokens } from '../../design/colors';

export const TAB_ITEMS = [
  { name: 'home', label: 'Home', icon: '⌂' },
  { name: 'health', label: 'Health', icon: '♡' },
  { name: 'connect', label: 'Connect', icon: '⚭' },
  { name: 'services', label: 'Services', icon: '▣' },
  { name: 'profile', label: 'Profile', icon: '◔' },
] as const;

/**
 * DESIGN_SYSTEM.md §11 / ADR 0020: five quiet tabs (spec §17,
 * "content is the hero; navigation is infrastructure") — 62×46px min
 * targets, 11.5px labels, inactive at .6 opacity, active at full opacity
 * + weight 600, never a fill or a pill. Colours read from `phoneTokens`
 * (the ADR's own gap against the spike: previously hard-coded hex in
 * `_layout.tsx`'s `StyleSheet`).
 *
 * v2's own `.tabs` has no background chrome of its own; this bar keeps a
 * subtle fill + hairline (unchanged behaviour from the spike, only the
 * colour source moved) so the bar reads apart from scrolling content on
 * a phone — flagged as a discrepancy against v2 in the golden-path
 * report rather than silently removed, since removing it is a visual
 * decision beyond "read colours from tokens".
 */
export function BottomNavigation() {
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

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 8,
    backgroundColor: '#1c1728',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: phoneTokens.g,
  },
  tab: { alignItems: 'center', gap: 3, minWidth: 62, minHeight: 46, paddingVertical: 2 },
  icon: { fontSize: 18, color: phoneTokens.c, opacity: 0.6 },
  iconActive: { opacity: 1 },
  label: { fontSize: 11.5, color: phoneTokens.c, opacity: 0.6 },
  labelActive: { opacity: 1, fontWeight: '600' },
});
