import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Animated, { useAnimatedScrollHandler, useSharedValue } from 'react-native-reanimated';

import { AmbientBackground } from '../../components/ambient/AmbientBackground';
import { AIComposer } from '../../components/ai/AIComposer';
import { NuraCard } from '../../components/cards/NuraCard';
import { EditorialHeadline } from '../../components/text/EditorialHeadline';
import { LoadingState } from '../../components/states/LoadingState';
import { EmptyState } from '../../components/states/EmptyState';
import { askFixtureAnswer } from '../../features/home/mock';
import { staggerCards } from '../../components/motion/motionTokens';
import { getCurrentProfileId } from '../../lib/api/config';
import { getProfile } from '../../lib/api/profile';
import { getProfileState } from '../../lib/api/state';
import { getFeed } from '../../lib/api/feed';
import { getMedicationReminder, type MedicationReminder } from '../../lib/api/reminder';
import type { Profile } from '../../domain/profile';
import type { ProfileState } from '../../domain/profileState';
import type { FeedItem } from '../../domain/feed';

const AnimatedScrollView = Animated.createAnimatedComponent(ScrollView);

/**
 * Scene 15: Home, recomposed from real state (C4) — the greeting, the
 * headline, the primary insight card and the feed below it all come
 * from `GET /profiles/{id}/state` and `GET /profiles/{id}/feed`, not
 * `features/home/mock.ts` (gone from this screen; kept only as the
 * `AIComposer`'s own fixture until C5 wires that live too). A cold load
 * reads these plainly; the live-events version (`STATE_SNAPSHOT`/
 * `STATE_DELTA` off a run, updating this same screen without a refetch)
 * is a follow-on once a run can be *triggered* from Home itself — today
 * every run starts from `add-paper`/`ask`, so there is no in-place delta
 * to drive yet, only the cold read this screen now does for real.
 */
export default function HomeScreen() {
  const router = useRouter();
  const { width, height } = useWindowDimensions();
  const scrollY = useSharedValue(0);
  const [doseTaken, setDoseTaken] = useState(false);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [state, setState] = useState<ProfileState | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [reminder, setReminder] = useState<MedicationReminder | null>(null);

  useEffect(() => {
    const profileId = getCurrentProfileId();
    if (!profileId) {
      router.replace('/welcome');
      return;
    }
    (async () => {
      const [p, s, f, r] = await Promise.all([
        getProfile(profileId),
        getProfileState(profileId).catch(() => null),
        getFeed(profileId).catch(() => ({ audience: '', items: [] })),
        getMedicationReminder(profileId),
      ]);
      setProfile(p);
      setState(s);
      setFeed(f.items);
      setReminder(r);
      setLoading(false);
    })();
  }, [router]);

  const scrollHandler = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });

  const hour = new Date().getHours();
  const timeOfDay = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
  const greeting = profile ? `Good ${timeOfDay}, ${profile.displayName}` : '';
  const initial = profile?.displayName?.[0]?.toUpperCase() ?? '?';
  const headline = state?.line ?? 'How are you today?';

  return (
    <View style={styles.root} testID="home-screen">
      <AmbientBackground width={width} height={height} scrollY={scrollY} />
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{initial}</Text>
          </View>
          <View style={styles.headerText}>
            <Text style={styles.greeting}>{greeting}</Text>
            <Text style={styles.prompt}>How are you today?</Text>
          </View>
          <Pressable style={styles.notWell} accessibilityRole="button" testID="not-well">
            <Text style={styles.notWellText}>Not well?</Text>
          </Pressable>
        </View>

        {loading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator color="#fbf6f0" />
          </View>
        ) : (
          <AnimatedScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            onScroll={scrollHandler}
            scrollEventThrottle={16}
            showsVerticalScrollIndicator={false}
          >
            <Text style={styles.kicker}>Today</Text>
            <EditorialHeadline text={headline} />

            {state ? (
              <NuraCard variant="ai-summary" tier="primary" enterIndex={0} staggerMs={staggerCards} testID="state-card">
                <Text style={styles.stateWord}>{state.word}</Text>
                <Text style={styles.stateLine}>{state.line}</Text>
              </NuraCard>
            ) : (
              <EmptyState
                title="Nura doesn’t have a reading yet."
                why="Add a paper and Nura can start keeping track."
                ctaLabel="Add a paper"
                onPress={() => router.push('/add-paper')}
                testID="state-empty"
              />
            )}

            {feed.map((item, i) => (
              <NuraCard
                key={item.itemId}
                variant={item.type === 'now' ? 'reminder' : 'document'}
                tier="secondary"
                enterIndex={i + 1}
                staggerMs={staggerCards}
                testID={`feed-card-${item.itemId}`}
              >
                <Text style={styles.docTitle}>{item.headline}</Text>
                {item.body.map((line, j) => (
                  <Text key={j} style={styles.docSubtitle}>
                    {line}
                  </Text>
                ))}
              </NuraCard>
            ))}

            {reminder && !reminder.taken ? (
              <NuraCard
                variant="reminder"
                tier="secondary"
                onPress={() => setDoseTaken((v) => !v)}
                enterIndex={feed.length + 1}
                staggerMs={staggerCards}
                testID="reminder-card"
              >
                <Text style={styles.docTitle}>{`${reminder.name} · ${reminder.time}`}</Text>
                <Text style={styles.docSubtitle}>{reminder.instruction}</Text>
              </NuraCard>
            ) : null}

            <Pressable style={styles.addPaper} onPress={() => router.push('/add-paper')} accessibilityRole="button" accessibilityLabel="Add a paper" testID="home-add-paper">
              <Text style={styles.addPaperText}>+ Add a paper</Text>
            </Pressable>

            <View style={{ height: 8 }} />
          </AnimatedScrollView>
        )}

        <View style={styles.dock}>
          <AIComposer answer={askFixtureAnswer} onOpenReadings={() => router.push('/report')} onOpenAsk={() => router.push('/ask')} testID="ai-composer" />
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#1f1731' },
  safe: { flex: 1 },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
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
  stateWord: { color: '#fbf6f0', fontSize: 20, fontWeight: '500', textTransform: 'capitalize' },
  stateLine: { color: 'rgba(251,246,240,0.85)', fontSize: 15, marginTop: 4 },
  docTitle: { color: '#fbf6f0', fontSize: 16, fontWeight: '400' },
  docSubtitle: { color: 'rgba(251,246,240,0.75)', fontSize: 14, marginTop: 2 },
  addPaper: { minHeight: 48, borderRadius: 999, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center' },
  addPaperText: { color: '#fbf6f0', fontSize: 14.5 },
  dock: { paddingHorizontal: 20, paddingBottom: 10, paddingTop: 4 },
});
