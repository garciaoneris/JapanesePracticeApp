export interface Kanji {
  char: string;
  strokes: number;
  jlpt: 4 | 5;
  on: string[];
  kun: string[];
  meanings: string[];
  svg: string;
  words: string[];
}

export interface Word {
  id: string;
  jp: string;
  reading: string;
  meanings: string[];
  pos: string[];
  kanji: string[];
  examples: { jp: string; en: string }[];
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
