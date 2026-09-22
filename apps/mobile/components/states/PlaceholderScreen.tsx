import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

/**
 * A calm placeholder for a tab this spike does not build (Home only —
 * mobile-architecture.md §5). Says plainly that it isn't built yet,
 * never a blank screen or a crash.
 */
export function PlaceholderScreen({ title, line }: { title: string; line: string }) {
  return (
    <SafeAreaView style={styles.root} testID={`placeholder-${title.toLowerCase()}`}>
      <View style={styles.center}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.line}>{line}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#1f1731' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40, gap: 10 },
  title: { color: '#fbf6f0', fontSize: 22, fontWeight: '400' },
  line: { color: 'rgba(251,246,240,0.68)', fontSize: 14.5, textAlign: 'center', lineHeight: 21 },
});
