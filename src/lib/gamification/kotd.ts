/** Kanji-of-the-day picker. Deterministic per date so all devices show the
 *  same character, preferring kanji the user hasn't mastered yet. Result
 *  is cached in meta key 'kotd' with its date stamp to avoid a recompute
 *  on every Home mount within the same day. */

import { getMeta, putMeta } from '../data/db';
import { todayIso } from './goal';

/** 32-bit unsigned hash of a string — cheap, stable, good enough for an
 *  index pick. Not cryptographic. */
function hash32(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

export interface KotdEntry {
  char: string;
  date: string;
}

/** Resolve today's kanji. `preferUnmastered` picks from kanji not yet in the
 *  mastered set, falling back to the full list if everything is mastered. */
export async function resolveKotd(
  allKanji: string[],
  masteredChars: Set<string>,
  now: Date = new Date(),
): Promise<string> {
  const today = todayIso(now);
  const cached = await getMeta<KotdEntry>('kotd');
  if (cached && cached.date === today && allKanji.includes(cached.char)) {
    return cached.char;
  }

  const pool = allKanji.filter((c) => !masteredChars.has(c));
  const source = pool.length > 0 ? pool : allKanji;
  if (source.length === 0) return '';
  const idx = hash32(today) % source.length;
  const char = source[idx];
  await putMeta('kotd', { char, date: today });
  return char;
}
