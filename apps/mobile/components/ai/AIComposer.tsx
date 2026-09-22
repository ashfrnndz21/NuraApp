import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { BlurView } from 'expo-blur';
import * as Haptics from 'expo-haptics';
import Animated, {
  useAnimatedKeyboard,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { runAskFixture, runExplainFixture, type AskFixtureAnswer, type NuraEvent } from '../../lib/ai/events';
import { cardEnter, fadeExit } from '../motion/motionTokens';
import { useReducedMotion } from '../motion/useReducedMotion';
import { IntelligenceOrb } from '../ambient/IntelligenceOrb';
import { useAIState } from './AIState';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  emphasis?: boolean;
}

export interface AIComposerProps {
  answer: AskFixtureAnswer;
  onOpenReadings: () => void;
  onOpenAsk: () => void;
  testID?: string;
}

/**
 * The docked composer (spec §9): the pill "Ask Nura anything · Speak"
 * expands in place, never a separate screen. Driven entirely by the
 * ADR 0019 §4 event stream — here a fixture with the same shape the
 * live `POST /profiles/{id}/runs` route will emit.
 */
export function AIComposer({ answer, onOpenReadings, onOpenAsk, testID }: AIComposerProps) {
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [chipsDisabled, setChipsDisabled] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const userEditedRef = useRef(false);
  const inputRef = useRef<TextInput>(null);
  const runRef = useRef<{ cancel: () => void } | null>(null);
  const consumeEvent = useAIState((s) => s.consumeEvent);
  const setListening = useAIState((s) => s.setListening);
  const reset = useAIState((s) => s.reset);
  const errorMessage = useAIState((s) => s.errorMessage);
  const reducedMotion = useReducedMotion();

  const opacity = useSharedValue(0);
  const translateY = useSharedValue(14);
  const pillOpacity = useSharedValue(1);

  const keyboard = useAnimatedKeyboard();
  const keyboardStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: -keyboard.height.value }],
  }));

  const appendDelta = useCallback((messageId: string, role: 'user' | 'assistant', delta: string, emphasis = false) => {
    setMessages((prev) => {
      const existing = prev.find((m) => m.id === messageId);
      if (existing) {
        return prev.map((m) => (m.id === messageId ? { ...m, text: (m.text + delta).trimStart() } : m));
      }
      return [...prev, { id: messageId, role, text: delta.trimStart(), emphasis }];
    });
  }, []);

  const onEvent = useCallback(
    (event: NuraEvent) => {
      consumeEvent(event);
      if (event.type === 'TEXT_MESSAGE_START') {
        setMessages((prev) => (prev.find((m) => m.id === event.messageId) ? prev : [...prev, { id: event.messageId, role: event.role, text: '' }]));
      }
      if (event.type === 'TEXT_MESSAGE_CONTENT') {
        // The entry always exists by now (TEXT_MESSAGE_START precedes it in this stream);
        // the role passed here is only a defensive fallback.
        appendDelta(event.messageId, 'assistant', event.delta);
      }
      if (event.type === 'STATE_DELTA' && Array.isArray(event.patch.chips)) {
        setChips(event.patch.chips as string[]);
        setChipsDisabled(false);
      }
    },
    [consumeEvent, appendDelta]
  );

  const openComposer = () => {
    if (expanded) return;
    setExpanded(true);
    setMessages([]);
    setChips([]);
    setChipsDisabled(false);
    setExplainOpen(false);
    setDraft('');
    userEditedRef.current = false;
    setListening();
    setTimeout(() => inputRef.current?.focus(), 0);
    opacity.value = reducedMotion ? 1 : withTiming(1, { duration: cardEnter });
    translateY.value = reducedMotion ? 0 : withTiming(0, { duration: cardEnter });
    pillOpacity.value = reducedMotion ? 0 : withTiming(0, { duration: fadeExit });

    const run = runAskFixture(answer, onEvent);
    runRef.current = run;
  };

  const closeComposer = () => {
    runRef.current?.cancel();
    runRef.current = null;
    setExpanded(false);
    reset();
    opacity.value = reducedMotion ? 0 : withTiming(0, { duration: fadeExit });
    pillOpacity.value = reducedMotion ? 1 : withTiming(1, { duration: cardEnter });
  };

  useEffect(() => () => runRef.current?.cancel(), []);

  useEffect(() => {
    if (userEditedRef.current) return;
    const userMsg = messages.find((m) => m.role === 'user');
    if (userMsg) setDraft(userMsg.text);
  }, [messages]);

  const handleChip = (chip: string) => {
    if (chipsDisabled) return;
    setChipsDisabled(true);
    if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    if (chip === 'Explain') {
      setExplainOpen(true);
      const run = runExplainFixture(answer.explain, onEvent);
      runRef.current = run;
      return;
    }
    if (chip === answer.chips[1]) {
      closeComposer();
      onOpenReadings();
      return;
    }
    closeComposer();
    onOpenAsk();
  };

  const composerStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));
  const pillStyle = useAnimatedStyle(() => ({ opacity: pillOpacity.value }));

  return (
    <Animated.View style={keyboardStyle} testID={testID}>
      <View style={styles.stack}>
        <Animated.View style={[pillStyle, expanded && styles.hidden]} pointerEvents={expanded ? 'none' : 'auto'}>
          <Pressable
            style={styles.pill}
            onPress={openComposer}
            accessibilityRole="button"
            accessibilityLabel="Ask Nura anything"
            testID="composer-pill"
          >
            <Text style={styles.pillText}>Ask Nura anything</Text>
            <View style={styles.speakChip}>
              <Text style={styles.speakText}>🎙 Speak</Text>
            </View>
          </Pressable>
        </Animated.View>

        {expanded && (
          <Animated.View style={[styles.expanded, composerStyle]} testID="composer-expanded">
            {Platform.OS !== 'web' ? (
              <BlurView intensity={30} tint="dark" style={StyleSheet.absoluteFill} />
            ) : (
              <View style={[StyleSheet.absoluteFill, styles.webBackdrop]} />
            )}
            <View style={styles.askRow}>
              <IntelligenceOrb size="sm" />
              <TextInput
                ref={inputRef}
                style={styles.input}
                placeholder="Ask Nura anything"
                placeholderTextColor="rgba(251,246,240,0.55)"
                value={draft}
                onChangeText={(t) => {
                  userEditedRef.current = true;
                  setDraft(t);
                }}
                onFocus={() => useAIState.getState().state === 'idle' && setListening()}
                returnKeyType="send"
                testID="composer-input"
              />
              <Pressable onPress={closeComposer} accessibilityRole="button" accessibilityLabel="Close" testID="composer-close">
                <Text style={styles.close}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.body}>
              {messages
                .filter((m) => m.role === 'assistant')
                .map((m, i) => (
                  <Text key={m.id} style={[styles.answer, i === 1 && styles.question]} testID="composer-answer">
                    {m.text}
                  </Text>
                ))}
              {errorMessage ? (
                <Text style={styles.error} testID="composer-error">
                  {errorMessage} Try again.
                </Text>
              ) : null}

              {chips.length > 0 && !explainOpen && (
                <View style={styles.chips} testID="composer-chips">
                  {chips.map((chip) => (
                    <Pressable
                      key={chip}
                      style={[styles.chip, chipsDisabled && styles.chipDisabled]}
                      onPress={() => handleChip(chip)}
                      disabled={chipsDisabled}
                      accessibilityRole="button"
                      testID={`composer-chip-${chip}`}
                    >
                      <Text style={styles.chipText}>{chip}</Text>
                    </Pressable>
                  ))}
                </View>
              )}
            </View>
          </Animated.View>
        )}
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  stack: { position: 'relative' },
  hidden: { position: 'absolute', left: 0, right: 0 },
  pill: {
    minHeight: 60,
    borderRadius: 28,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
  },
  pillText: { color: '#fbf6f0', fontSize: 16, fontWeight: '300' },
  speakChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fbf6f0',
    borderRadius: 999,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  speakText: { color: '#2b2140', fontSize: 12.5, fontWeight: '600' },
  expanded: {
    borderRadius: 28,
    padding: 16,
    paddingTop: 14,
    gap: 12,
    backgroundColor: 'rgba(27,20,44,0.93)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
    overflow: 'hidden',
  },
  webBackdrop: { backgroundColor: 'rgba(27,20,44,0.93)' },
  askRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  input: { flex: 1, color: '#fbf6f0', fontSize: 16 },
  close: { color: 'rgba(251,246,240,0.7)', fontSize: 16, padding: 6 },
  body: { gap: 10 },
  answer: { color: '#fbf6f0', fontSize: 16.5, fontWeight: '300', lineHeight: 22 },
  question: { color: 'rgba(251,246,240,0.85)' },
  error: { color: '#f4a0b6', fontSize: 15 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 15,
    paddingVertical: 9,
    minHeight: 42,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.14)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
    justifyContent: 'center',
  },
  chipDisabled: { opacity: 0.5 },
  chipText: { color: '#fbf6f0', fontSize: 14 },
});
