import { getAllBestScores, getMeta } from './db';
import type { Segment } from './types';

/** A kanji is "known" / "practiced" once its best morph score reaches this
 * threshold. Matches the value chosen in the plan (answer to AskUserQuestion). */
export const KNOWN_THRESHOLD = 80;

const CJK_START = 0x4e00;
const CJK_END = 0x9fff;

function isKanjiChar(ch: string): boolean {
  const cp = ch.codePointAt(0);
  if (cp === undefined) return false;
  return cp >= CJK_START && cp <= CJK_END;
}

/** Returns the set of kanji the user has practiced to the mastery threshold. */
export async function loadKnownKanji(): Promise<Set<string>> {
  // Native mode: treat ALL kanji as known.
  const native = await getMeta<boolean>('native-mode');
  if (native) {
    const { bundle } = await import('./bundle');
    const b = bundle();
    return new Set(Object.keys(b.kanji));
  }
  // Normal mode: only kanji with score >= threshold.
  const scores = await getAllBestScores();
  const out = new Set<string>();
  for (const [char, score] of scores) {
    if (score >= KNOWN_THRESHOLD) out.add(char);
  }
  return out;
}

/** True iff every kanji character inside `text` is in `known` or equals the
 * optional `alsoKnown` (the kanji currently being learned, treated as known
 * even before it crosses the threshold). Kana, punctuation, Latin — all fine. */
export function textUsesOnlyKnown(
  text: string,
  known: ReadonlySet<string>,
  alsoKnown?: string,
): boolean {
  for (const ch of text) {
    if (!isKanjiChar(ch)) continue;
    if (alsoKnown && ch === alsoKnown) continue;
    if (!known.has(ch)) return false;
  }
  return true;
}

/** Same as textUsesOnlyKnown, but operates on pre-segmented furigana data. */
export function sentenceUsesOnlyKnown(
  segs: Segment[],
  known: ReadonlySet<string>,
  alsoKnown?: string,
): boolean {
  for (const s of segs) {
    if (!textUsesOnlyKnown(s.t, known, alsoKnown)) return false;
  }
  return true;
}

export interface FilterResult<E> {
  kept: E[];
  tooAdvanced: boolean;
}

/** Keep only examples whose segments pass `sentenceUsesOnlyKnown`. If nothing
 * passes, fall back to the two shortest originals and flag `tooAdvanced = true`
 * so the caller can display a hint. */
export function filterExamples<E extends { segs: Segment[]; jp?: string }>(
  examples: E[],
  known: ReadonlySet<string>,
  alsoKnown?: string,
): FilterResult<E> {
  const kept: E[] = [];
  for (const ex of examples) {
    if (sentenceUsesOnlyKnown(ex.segs, known, alsoKnown)) kept.push(ex);
  }
  if (kept.length > 0) return { kept, tooAdvanced: false };

  // Fallback: show the 2 shortest originals so the learner has *something*,
  // with a hint that they're still beyond the current level.
  const sorted = [...examples].sort((a, b) => (a.jp?.length ?? 0) - (b.jp?.length ?? 0));
  return { kept: sorted.slice(0, 2), tooAdvanced: true };
}
