import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { NuraCard } from '../components/cards/NuraCard';
import { EmptyState } from '../components/states/EmptyState';
import { ScreenBackground } from '../components/layout/ScreenBackground';
import { ApiRefusalError, errorStateFromRefusal } from '../lib/api/refusals';
import { phoneTokens, semanticColors } from '../design/colors';
import * as typography from '../design/typography';
import { getCurrentProfileId } from '../lib/api/config';
import { confirmReviewCard } from '../lib/api/reviewCards';
import { getReviewCardQueue, updateReviewCardInQueue } from '../lib/media/pendingPaper';
import { canSubmitReport, buildConfirmDecisions, fieldNeedsAnswer } from '../lib/report/confirmLogic';
import { reportKickerLine, hasNoFields } from '../lib/report/cardCopy';
import { fieldLabel, isResultRow } from '../lib/report/fieldLabels';
import { displayFieldValue } from '../lib/dates';
import type { FieldDecision, ReviewCard, ReviewField } from '../domain/reviewCard';

/**
 * Scene 7 (v2 frame 07): the report table, from the confirmed review
 * card's own fields — nothing recomputed, nothing a model wrote.
 *
 * B5 (independent review of PR #332): every paper picked at once gets
 * its own table here (`getReviewCardQueue()`), not only the last one —
 * `reading.tsx` now appends every finished card instead of overwriting
 * one slot. B4: "Looks right" is gated per card on every `needsConfirm`,
 * still-`proposed` field having an explicit answer first
 * (`lib/report/confirmLogic.ts`) — an unanswered flagged field is
 * highlighted, never silently defaulted to confirmed. B6: renders the
 * paper's own printed range (`field.range`), its printed label
 * (`labelOnPaper`), the card's own `notice`/`documentKind`, and a field
 * Nura could not read at all (`unreadable`).
 */
export default function Report() {
  const router = useRouter();
  const cards = useMemo(() => getReviewCardQueue(), []);
  const [cardsState, setCardsState] = useState<ReviewCard[]>(cards);
  const [decisionsByCard, setDecisionsByCard] = useState<Record<string, Record<string, FieldDecision>>>({});
  const [submittedCards, setSubmittedCards] = useState<Set<string>>(new Set());
  const [busyCardId, setBusyCardId] = useState<string | null>(null);
  const [attemptedCardId, setAttemptedCardId] = useState<string | null>(null);
  const [errorByCard, setErrorByCard] = useState<Record<string, { title: string; why: string }>>({});

  if (cardsState.length === 0) {
    return (
      <ScreenBackground style={styles.screen}>
        <EmptyState
          title="No paper is waiting for a table yet."
          why="Add a paper first and Nura will read it into a table here."
          ctaLabel="Add a paper"
          onPress={() => router.replace('/add-paper')}
          testID="report-empty"
        />
      </ScreenBackground>
    );
  }

  const setDecision = (cardId: string, fieldId: string, decision: FieldDecision) =>
    setDecisionsByCard((all) => ({ ...all, [cardId]: { ...all[cardId], [fieldId]: decision } }));

  const submitCard = async (card: ReviewCard) => {
    const decisions = decisionsByCard[card.cardId] ?? {};
    if (!canSubmitReport(card, decisions)) {
      setAttemptedCardId(card.cardId);
      return;
    }
    const profileId = getCurrentProfileId();
    if (!profileId) return;
    setBusyCardId(card.cardId);
    setErrorByCard((all) => {
      const { [card.cardId]: _drop, ...rest } = all;
      return rest;
    });
    try {
      const updated = await confirmReviewCard(profileId, card.cardId, {
        decisions: buildConfirmDecisions(card, decisions),
      });
      updateReviewCardInQueue(updated);
      setCardsState((all) => all.map((c) => (c.cardId === updated.cardId ? updated : c)));
      setSubmittedCards((s) => new Set(s).add(card.cardId));
    } catch (err) {
      // A real crash this screen used to have (independent review of PR #332, found live):
      // an unhandled ApiRefusalError from confirmReviewCard reached React as an uncaught
      // error and took the whole screen down. Never again — surfaced per card instead.
      setErrorByCard((all) => ({
        ...all,
        [card.cardId]:
          err instanceof ApiRefusalError
            ? errorStateFromRefusal(err)
            : { title: "We couldn't save that.", why: 'Nothing was lost. Try again.' },
      }));
    } finally {
      setBusyCardId(null);
    }
  };

  const allSubmitted = cardsState.every((c) => submittedCards.has(c.cardId));

  return (
    <ScreenBackground style={styles.screen}>
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.pageKicker} testID="report-count">
          {cardsState.length > 1 ? `${cardsState.length} papers to look over` : '1 paper to look over'}
        </Text>

        {cardsState.map((card, cardIndex) => (
          <ReportCard
            key={card.cardId}
            card={card}
            cardIndex={cardIndex}
            total={cardsState.length}
            decisions={decisionsByCard[card.cardId] ?? {}}
            setDecision={(fieldId, decision) => setDecision(card.cardId, fieldId, decision)}
            onSubmit={() => submitCard(card)}
            busy={busyCardId === card.cardId}
            submitted={submittedCards.has(card.cardId)}
            showUnanswered={attemptedCardId === card.cardId}
            error={errorByCard[card.cardId] ?? null}
          />
        ))}
      </ScrollView>

      {allSubmitted ? (
        <Pressable
          style={styles.continueCta}
          onPress={() => router.push('/insight')}
          accessibilityRole="button"
          accessibilityLabel="What it means"
          testID="report-continue"
        >
          <Text style={styles.ctaText}>What it means</Text>
        </Pressable>
      ) : null}
    </ScreenBackground>
  );
}

function ReportCard({
  card,
  cardIndex,
  total,
  decisions,
  setDecision,
  onSubmit,
  busy,
  submitted,
  showUnanswered,
  error,
}: {
  card: ReviewCard;
  cardIndex: number;
  total: number;
  decisions: Record<string, FieldDecision>;
  setDecision: (fieldId: string, decision: FieldDecision) => void;
  onSubmit: () => void;
  busy: boolean;
  submitted: boolean;
  showUnanswered: boolean;
  error: { title: string; why: string } | null;
}) {
  const router = useRouter();
  const outsideCount = card.fields.filter((f) => f.needsConfirm).length;
  const canSubmit = !hasNoFields(card) && card.fields.filter((f) => fieldNeedsAnswer(f, decisions)).length === 0;

  // BL-1 (second independent review of PR #332): a card with nothing read from it gets its
  // own honest EmptyState — never "0 readings, all as printed." (a sentence that reads as a
  // clean bill of health for a paper Nura never actually read) and never a "Looks right" with
  // nothing to look at.
  if (hasNoFields(card)) {
    return (
      <NuraCard
        variant="metric"
        tier="primary"
        sharedTransitionTag={`paper-${card.artifactId}`}
        testID={`report-card-${card.cardId}`}
      >
        {total > 1 ? (
          <Text style={styles.cardKicker}>
            Paper {cardIndex + 1} of {total}
          </Text>
        ) : null}
        <EmptyState
          title="Nura could not read any numbers from this paper."
          why="Try retaking the photo in daylight, holding it flat, or choose a clearer photo. It may also not be a health paper Nura can read yet."
          ctaLabel="Add a paper"
          onPress={() => router.replace('/add-paper')}
          testID={`report-card-empty-${card.cardId}`}
        />
      </NuraCard>
    );
  }

  return (
    <NuraCard
      variant="metric"
      tier="primary"
      sharedTransitionTag={`paper-${card.artifactId}`}
      testID={`report-card-${card.cardId}`}
    >
      {total > 1 ? (
        <Text style={styles.cardKicker}>
          Paper {cardIndex + 1} of {total}
        </Text>
      ) : null}
      <Text style={styles.kicker}>{reportKickerLine(card)}</Text>
      <Text style={styles.headline}>
        {outsideCount > 0
          ? `${outsideCount} of ${card.fields.length} need a second look.`
          : `${card.fields.length} readings, all as printed.`}
      </Text>

      {card.notice && card.notice.length > 0 ? (
        <View style={styles.noticeBox} testID={`report-notice-${card.cardId}`}>
          {card.notice.map((n, i) => (
            <Text key={i} style={styles.noticeText}>
              {n}
            </Text>
          ))}
        </View>
      ) : null}

      {/* "Results first" (web/src/onboarding/review.ts's own split): a measured result (a
          unit or a printed range) before an administrative line (a name, a date, a facility)
          — never mixed in position order, which is how a paper happens to print them. */}
      {[...card.fields]
        .sort((a, b) => Number(isResultRow(b)) - Number(isResultRow(a)))
        .map((field) => (
          <FieldRow
            key={field.fieldId}
            field={field}
            decision={decisions[field.fieldId]}
            onDecide={(d) => setDecision(field.fieldId, d)}
            highlight={showUnanswered && fieldNeedsAnswer(field, decisions)}
          />
        ))}

      <Text style={styles.caption}>Ranges are the ones printed on your paper. This is not a doctor’s advice.</Text>

      {submitted ? (
        <View style={styles.doneRow} testID={`report-done-${card.cardId}`}>
          <Text style={styles.doneText}>Looks right — saved.</Text>
        </View>
      ) : (
        <Pressable
          style={[styles.cta, busy && styles.ctaBusy, !canSubmit && styles.ctaDisabled]}
          disabled={busy}
          onPress={onSubmit}
          accessibilityRole="button"
          accessibilityLabel="Looks right"
          accessibilityState={{ disabled: !canSubmit }}
          testID={`report-confirm-all-${card.cardId}`}
        >
          <Text style={styles.ctaText}>{busy ? 'Saving…' : 'Looks right'}</Text>
        </Pressable>
      )}
      {showUnanswered && !canSubmit ? (
        <Text style={styles.gateWarning} testID={`report-gate-warning-${card.cardId}`}>
          Answer every flagged reading before continuing.
        </Text>
      ) : null}
      {error ? (
        <View testID={`report-card-error-${card.cardId}`}>
          <Text style={styles.gateWarning}>{error.title}</Text>
          <Text style={styles.caption}>{error.why}</Text>
        </View>
      ) : null}
    </NuraCard>
  );
}

function FieldRow({
  field,
  decision,
  onDecide,
  highlight,
}: {
  field: ReviewField;
  decision: FieldDecision | undefined;
  onDecide: (d: FieldDecision) => void;
  highlight: boolean;
}) {
  const needsAnswer = field.needsConfirm && field.state === 'proposed' && decision === undefined;
  const settledElsewhere = field.state !== 'proposed';
  const label = fieldLabel(field);
  const isResult = isResultRow(field);

  // Patient-visible defect (third independent review of PR #332, section 29 — never a raw
  // token on screen): this used to show `field.labelOnPaper ?? field.attribute` (a raw
  // backend code, e.g. "facility") as the title and `field.subject` (e.g. "lipid_panel") as
  // a subtitle under every row, result or not. Now: an admin row (no unit, no range — a
  // name, a date, a facility) shows only its plain label and its value, nothing numeric; a
  // result row shows its plain label, the value and unit, the range on paper, and the flag
  // — never its subject/attribute token, on either kind of row.
  if (!isResult) {
    return (
      <View style={[styles.adminRow, highlight && styles.fieldCardHighlight]} testID={`report-field-${field.fieldId}`}>
        <Text style={styles.adminLabel}>{label}</Text>
        <Text style={styles.adminValue}>{field.unreadable ? 'Could not read' : displayFieldValue(field.value)}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.fieldCard, highlight && styles.fieldCardHighlight]} testID={`report-field-${field.fieldId}`}>
      <View style={styles.fieldRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.fieldTitle}>{label}</Text>
        </View>
        <View style={styles.valueBlock}>
          {field.unreadable ? (
            <Text style={styles.unreadableText}>Could not read</Text>
          ) : (
            <Text style={styles.valueText}>
              {displayFieldValue(field.value)}
              {field.unit ? <Text style={styles.unitText}> {field.unit}</Text> : null}
            </Text>
          )}
          {field.range ? <RangeFlag value={field.value} range={field.range} /> : null}
        </View>
      </View>

      {field.range?.text ? <Text style={styles.rangeText}>range on paper: {field.range.text}</Text> : null}

      {field.unreadable && field.prompt ? (
        <View style={styles.uncertain}>
          {field.prompt.map((line, i) => (
            <Text key={i} style={styles.promptText}>
              {line}
            </Text>
          ))}
        </View>
      ) : null}

      {needsAnswer || (field.needsConfirm && !settledElsewhere) ? (
        <View style={styles.uncertain}>
          {(field.prompt ?? []).map((line, i) => (
            <Text key={i} style={styles.promptText}>
              {line}
            </Text>
          ))}
          <View style={styles.rowButtons}>
            <Pressable
              style={[styles.smallBtn, decision === 'confirmed' && styles.smallBtnActive]}
              onPress={() => onDecide('confirmed')}
              accessibilityRole="button"
              accessibilityLabel="This is right"
              testID={`report-confirm-${field.fieldId}`}
            >
              <Text style={styles.smallBtnText}>This is right</Text>
            </Pressable>
            <Pressable
              style={[styles.smallBtn, decision === 'rejected' && styles.smallBtnActive]}
              onPress={() => onDecide('rejected')}
              accessibilityRole="button"
              accessibilityLabel="Not right"
              testID={`report-reject-${field.fieldId}`}
            >
              <Text style={styles.smallBtnText}>Not right</Text>
            </Pressable>
          </View>
          {highlight ? (
            <Text style={styles.highlightText} testID={`report-unanswered-${field.fieldId}`}>
              This one still needs your answer.
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

/** A-049: Above/Below/In range, from the paper's own printed low/high — never a clinical judgement. */
function RangeFlag({ value, range }: { value: unknown; range: NonNullable<ReviewField['range']> }) {
  const numeric = typeof value === 'number' ? value : typeof value === 'string' ? parseFloat(value) : NaN;
  if (Number.isNaN(numeric) || (range.low === null && range.high === null)) return null;
  const above = range.high !== null && numeric > range.high;
  const below = range.low !== null && numeric < range.low;
  const label = above ? 'Above' : below ? 'Below' : 'In range';
  return (
    <View style={[styles.flagPill, (above || below) && styles.flagPillOutside]}>
      <Text style={[styles.flagText, (above || below) && styles.flagTextOutside]}>{label}</Text>
    </View>
  );
}


const styles = StyleSheet.create({
  screen: { paddingHorizontal: 20, paddingTop: 60 },
  body: { gap: 16, paddingBottom: 20 },
  pageKicker: { color: 'rgba(251,246,240,0.7)', fontSize: typography.fontSize[13] },
  cardKicker: { color: phoneTokens.c, fontSize: typography.fontSize[12.5], fontWeight: '600', opacity: 0.8 },
  kicker: { color: 'rgba(251,246,240,0.7)', fontSize: typography.fontSize[13], marginTop: 2 },
  headline: { color: phoneTokens.c, fontSize: typography.fontSize[22], fontWeight: '300', lineHeight: 27, marginBottom: 4, marginTop: 4 },
  noticeBox: { backgroundColor: 'rgba(243,181,98,0.14)', borderRadius: 14, padding: 10, gap: 4 },
  noticeText: { color: semanticColors.watch, fontSize: typography.fontSize[12.5] },
  fieldCard: { backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: 16, padding: 12, gap: 6 },
  fieldCardHighlight: { borderWidth: 1.5, borderColor: semanticColors.act },
  fieldRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  fieldTitle: { color: phoneTokens.c, fontSize: typography.fontSize[16], fontWeight: '500' },
  adminRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 16,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  adminLabel: { color: 'rgba(251,246,240,0.7)', fontSize: typography.fontSize[13.5], flexShrink: 1 },
  adminValue: { color: phoneTokens.c, fontSize: typography.fontSize[14], fontWeight: '500', flexShrink: 1, textAlign: 'right' },
  valueBlock: { alignItems: 'flex-end', gap: 6 },
  valueText: { color: phoneTokens.c, fontSize: typography.fontSize[20], fontWeight: '600' },
  unreadableText: { color: 'rgba(251,246,240,0.6)', fontSize: typography.fontSize[14], fontStyle: 'italic' },
  unitText: { fontSize: typography.fontSize[12], fontWeight: '400', opacity: 0.75 },
  rangeText: { color: 'rgba(251,246,240,0.55)', fontSize: typography.fontSize[11.5] },
  flagPill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, backgroundColor: semanticColors.good },
  flagPillOutside: { backgroundColor: semanticColors.watch },
  flagText: { color: semanticColors.inkOnGood, fontSize: typography.fontSize[11.5], fontWeight: '600' },
  flagTextOutside: { color: semanticColors.inkOnTone },
  uncertain: { marginTop: 4, gap: 8 },
  promptText: { color: 'rgba(251,246,240,0.85)', fontSize: typography.fontSize[13.5], lineHeight: 18 },
  rowButtons: { flexDirection: 'row', gap: 8 },
  smallBtn: { flex: 1, minHeight: 40, borderRadius: 999, borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)', alignItems: 'center', justifyContent: 'center' },
  smallBtnActive: { backgroundColor: 'rgba(255,255,255,0.18)' },
  smallBtnText: { color: phoneTokens.c, fontSize: typography.fontSize[13] },
  highlightText: { color: semanticColors.act, fontSize: typography.fontSize[12] },
  caption: { color: 'rgba(251,246,240,0.55)', fontSize: typography.fontSize[12], marginTop: 4 },
  doneRow: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  doneText: { color: semanticColors.good, fontSize: typography.fontSize[14], fontWeight: '500' },
  cta: { minHeight: 52, borderRadius: 999, backgroundColor: phoneTokens.c, alignItems: 'center', justifyContent: 'center' },
  ctaBusy: { opacity: 0.7 },
  ctaDisabled: { opacity: 0.4 },
  continueCta: { minHeight: 56, borderRadius: 999, backgroundColor: phoneTokens.c, alignItems: 'center', justifyContent: 'center', marginVertical: 20 },
  ctaText: { color: semanticColors.inkOnLight, fontWeight: '600', fontSize: typography.fontSize[17] },
  gateWarning: { color: semanticColors.act, fontSize: typography.fontSize[12], marginTop: 4 },
});
