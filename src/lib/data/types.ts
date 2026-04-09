/** A "callout" is a (word, reading, sentence) triple the practice step uses
 * during the morph animation. We pre-compute a handful per kanji so we can
 * pick one at random and speak "reading → sentence". */
export interface Callout {
  wordJp: string;
  wordReading: string;
  wordMeaning: string;
  exJp: string;
  exEn: string;
}

export interface Kanji {
  char: string;
  strokes: number;
  /** Modern JLPT level: 5=N5 (easiest) … 1=N1 (hardest). 0 means ungraded —
   * not in any JLPT list but kept because it's in the jouyou/jinmeiyou set.
   * N3 is synthesized by splitting old KANJIDIC2 level 2 using school grade
   * (grades 1-4 → N3, grades 5-8 → N2). */
  jlpt: 0 | 1 | 2 | 3 | 4 | 5;
  /** KANJIDIC2 school grade used as a finer-grained complexity tiebreaker:
   * 1–6 = elementary (kyouiku), 8 = general jouyou, 9–10 = jinmeiyou,
   * 0 = unknown. */
  grade: number;
  on: string[];
  kun: string[];
  meanings: string[];
  svg: string;
  words: string[];
  callouts: Callout[];
}

/** Segment of an example sentence.
 *
 * - `r` (hiragana reading): only set when the segment contains kanji AND the
 *   reading is non-trivial. Pure-kana segments and "no-reading-available"
 *   kanji segments simply omit the field to keep the bundle small.
 * - `g` (English gloss): set when the segment matches a JMdict headword,
 *   giving the learner a word-level tooltip they can tap. */
export interface Segment {
  t: string;
  r?: string;
  g?: string;
}

export interface Example {
  /** English translation of `segs`. */
  en: string;
  /** Tokenized Japanese sentence. `segs.map(s => s.t).join('')` reconstructs
   * the original sentence exactly, so we don't store `jp` separately. Use
   * {@link exampleJp} when a joined string is needed. */
  segs: Segment[];
}

/** Join an example's segments back into the original Japanese sentence.
 * Cheaper than storing the joined form for all ~17k examples in the bundle. */
export function exampleJp(ex: Example): string {
  let out = '';
  for (const s of ex.segs) out += s.t;
  return out;
}

export interface Word {
  id: string;
  jp: string;
  reading: string;
  meanings: string[];
  kanji: string[];
  examples: Example[];
}

export interface Bundle {
  version: string;
  kanji: Record<string, Kanji>;
  words: Record<string, Word>;
}

export type Grade = 'again' | 'hard' | 'good' | 'easy';

export interface SrsState {
  id: string;
  kind: 'kanji' | 'word';
  ease: number;
  intervalDays: number;
  dueAt: number;
  reps: number;
  lapses: number;
}

/** One practice-morph attempt. Persisted to the `attempts` IndexedDB store. */
export interface Attempt {
  id?: number;
  char: string;
  score: number;
  strokeCount: number;        // how many strokes the user actually drew
  requiredStrokes: number;    // stroke count of the reference kanji
  ts: number;                 // Date.now() at the time of the attempt
}
