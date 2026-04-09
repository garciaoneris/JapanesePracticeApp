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
  jlpt: 4 | 5;
  on: string[];
  kun: string[];
  meanings: string[];
  svg: string;
  words: string[];
  callouts: Callout[];
}

/** Segment of an example sentence.
 *
 * - `r` (hiragana reading) is set only when the segment contains kanji the
 *   learner hasn't been introduced to yet (used for furigana).
 * - `g` (English gloss) is set when the segment matches a JMdict headword,
 *   giving the learner a word-level tooltip they can tap. */
export interface Segment {
  t: string;
  r: string | null;
  g?: string | null;
}

export interface Example {
  jp: string;
  en: string;
  segs: Segment[];
}

export interface Word {
  id: string;
  jp: string;
  reading: string;
  meanings: string[];
  /** Primary JMdict POS tag for each entry in `meanings`, same length and
   * order. Populated by the Python pipeline (fugashi + POS-aware sense
   * picker). Optional so older v5 caches still type-check. */
  meaning_pos?: string[];
  pos: string[];
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
