import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { useAnimatedScrollHandler, useSharedValue } from 'react-native-reanimated';

import { AmbientBackground } from '../../components/ambient/AmbientBackground';
import { AIComposer } from '../../components/ai/AIComposer';
import { ExpandableCard } from '../../components/cards/ExpandableCard';
import { InsightCard } from '../../components/cards/InsightCard';
import { MediaCard } from '../../components/cards/MediaCard';
import { NuraCard } from '../../components/cards/NuraCard';
import { ReminderCard } from '../../components/cards/ReminderCard';
import { BottomSheet } from '../../components/sheets/BottomSheet';
import { EditorialHeadline } from '../../components/text/EditorialHeadline';
import {
  askFixtureAnswer,
  bloodPressureExpand,
  bloodPressureVideo,
  bloodTest,
  eveningReminder,
  healthInsight,
  homeHeadline,
  tan,
} from '../../features/home/mock';
import { staggerCards } from '../../components/motion/motionTokens';

const LAB_RESULTS = [
  { label: 'LDL cholesterol', value: '4.0 mmol/L', range: 'paper range: up to 3.4', outside: true },
  { label: 'Total cholesterol', value: '6.2 mmol/L', range: 'paper range: up to 5.2', outside: true },
  { label: 'Triglycerides', value: '2.1 mmol/L', range: 'paper range: up to 1.7', outside: true },
  { label: 'Fasting glucose', value: '6.8 mmol/L', range: 'paper range: up to 6.0', outside: true },
  { label: 'HDL cholesterol', value: '1.3 mmol/L', range: 'paper range: above 1.0', outside: false },
];

const AnimatedScrollView = Animated.createAnimatedComponent(ScrollView);

export default function HomeScreen() {
  const { width, height } = useWindowDimensions();
  const scrollY = useSharedValue(0);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [doseTaken, setDoseTaken] = useState(false);

  const scrollHandler = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });

  return (
    <View style={styles.root} testID="home-screen">
      <AmbientBackground width={width} height={height} scrollY={scrollY} />
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{tan.initial}</Text>
          </View>
          <View style={styles.headerText}>
            <Text style={styles.greeting}>{tan.greeting}</Text>
            <Text style={styles.prompt}>{tan.prompt}</Text>
          </View>
          <Pressable style={styles.notWell} accessibilityRole="button" testID="not-well">
            <Text style={styles.notWellText}>Not well?</Text>
          </Pressable>
        </View>

        <AnimatedScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          onScroll={scrollHandler}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.kicker}>Today</Text>
          <EditorialHeadline text={homeHeadline} />

          <InsightCard
            title={healthInsight.title}
            segments={['Today', 'This week']}
            date={healthInsight.date}
            body={healthInsight.body}
            ctaLabel={healthInsight.cta}
            onPressCta={() => setSheetOpen(true)}
            enterIndex={0}
            staggerMs={staggerCards}
          />

          <ExpandableCard
            bpExplain={bloodPressureExpand.explain}
            possessive={bloodPressureExpand.possessive}
            onKeepForVisit={() => setSheetOpen(true)}
          />

          <NuraCard variant="document" tier="secondary" onPress={() => setSheetOpen(true)} enterIndex={1} staggerMs={staggerCards} testID="document-card">
            <Text style={styles.docTitle}>{bloodTest.title}</Text>
            <Text style={styles.docSubtitle}>{bloodTest.subtitle}</Text>
            <View style={styles.lookPill}>
              <Text style={styles.lookPillText}>{bloodTest.cta}</Text>
            </View>
          </NuraCard>

          <ReminderCard
            label={eveningReminder.label}
            done={doseTaken}
            onToggle={() => setDoseTaken((v) => !v)}
            enterIndex={2}
            staggerMs={staggerCards}
          />

          <MediaCard
            title={bloodPressureVideo.title}
            why={bloodPressureVideo.why}
            publisher={bloodPressureVideo.publisher}
            duration={bloodPressureVideo.duration}
            enterIndex={3}
            staggerMs={staggerCards}
          />

          <View style={{ height: 8 }} />
        </AnimatedScrollView>

        <View style={styles.dock}>
          <AIComposer
            answer={askFixtureAnswer}
            onOpenReadings={() => setSheetOpen(true)}
            onOpenAsk={() => setSheetOpen(true)}
            testID="ai-composer"
          />
        </View>
      </SafeAreaView>

      <BottomSheet visible={sheetOpen} onDismiss={() => setSheetOpen(false)} title="Blood test · 12 September" testID="lab-results-sheet">
        {LAB_RESULTS.map((r) => (
          <View key={r.label} style={styles.labRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.labLabel}>{r.label}</Text>
              <Text style={styles.labRange}>{r.range}</Text>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text style={styles.labValue}>{r.value}</Text>
              <Text style={[styles.labFlag, r.outside ? styles.labFlagOut : styles.labFlagIn]}>
                {r.outside ? 'Outside' : 'In range'}
              </Text>
            </View>
          </View>
        ))}
        <Text style={styles.note}>Ranges are the ones printed on your paper. This is not a doctor's advice.</Text>
      </BottomSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#1f1731' },
  safe: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingTop: 8, paddingBottom: 4 },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: '#fbf6f0', fontSize: 17, fontWeight: '500' },
  headerText: { flex: 1, gap: 1 },
  greeting: { color: 'rgba(251,246,240,0.82)', fontSize: 13.5 },
  prompt: { color: '#fbf6f0', fontSize: 17, fontWeight: '500' },
  notWell: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.1)' },
  notWellText: { color: '#fbf6f0', fontSize: 13 },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: 16, gap: 14 },
  kicker: { color: 'rgba(251,246,240,0.7)', fontSize: 14.5 },
  docTitle: { color: '#fbf6f0', fontSize: 16, fontWeight: '400' },
  docSubtitle: { color: 'rgba(251,246,240,0.75)', fontSize: 14 },
  lookPill: { alignSelf: 'flex-start', paddingHorizontal: 13, paddingVertical: 7, borderRadius: 999, backgroundColor: '#fbf6f0' },
  lookPillText: { color: '#2b2140', fontSize: 12.5, fontWeight: '600' },
  dock: { paddingHorizontal: 20, paddingBottom: 10, paddingTop: 4 },
  labRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    borderRadius: 16,
    padding: 12,
    backgroundColor: 'rgba(255,255,255,0.06)',
  },
  labLabel: { color: '#fbf6f0', fontSize: 15, fontWeight: '500' },
  labRange: { color: 'rgba(251,246,240,0.6)', fontSize: 12 },
  labValue: { color: '#fbf6f0', fontSize: 16, fontWeight: '600' },
  labFlag: { fontSize: 11, fontWeight: '600', marginTop: 2 },
  labFlagOut: { color: '#f3b562' },
  labFlagIn: { color: '#a9d3ae' },
  note: { color: 'rgba(251,246,240,0.6)', fontSize: 12, marginTop: 4 },
});
