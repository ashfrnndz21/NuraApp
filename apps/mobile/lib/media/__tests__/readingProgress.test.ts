import { readingProgressLabel, readingProgressPosition } from '../readingProgress';

describe('BL-2 — the reading-screen paper counter, fixed after the double-count bug', () => {
  test('one paper: no counter at all', () => {
    // total=1, and after the single paper is dequeued the queue is empty (0 remaining).
    expect(readingProgressLabel(1, 0)).toBeNull();
  });

  test('two papers: "Paper 1 of 2" then "Paper 2 of 2"', () => {
    // Screen for the first paper: dequeued, one remains in the queue.
    expect(readingProgressLabel(2, 1)).toBe('Paper 1 of 2');
    // Screen for the second paper: dequeued, none remain.
    expect(readingProgressLabel(2, 0)).toBe('Paper 2 of 2');
  });

  test('three papers walks 1, 2, 3 — never a count higher than total', () => {
    expect(readingProgressLabel(3, 2)).toBe('Paper 1 of 3');
    expect(readingProgressLabel(3, 1)).toBe('Paper 2 of 3');
    expect(readingProgressLabel(3, 0)).toBe('Paper 3 of 3');
  });

  test('readingProgressPosition never double-counts the current paper', () => {
    // The old bug: pendingPaperCount() read *before* dequeue (still includes the current
    // paper) plus 1 — for one paper that produced position 2, not 1.
    expect(readingProgressPosition(1, 0)).toBe(1);
    expect(readingProgressPosition(2, 1)).toBe(1);
    expect(readingProgressPosition(2, 0)).toBe(2);
  });
});
