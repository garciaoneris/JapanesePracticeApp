/** Kanji-of-the-day picker. Deterministic per date so all devices show the
 *  same character. Primary rule: map the day of the week to its classical
 *  element kanji (月曜日 → 月 etc.) so the pick has a built-in mnemonic.
 *  Falls back to a hashed pick from the unmastered pool when the day-of-week
 *  kanji isn't in the bundle. Cached in meta 'kotd' with its date stamp. */

import { getMeta, putMeta } from '../data/db';
import { todayIso } from './goal';

/** Day-of-week → element kanji, indexed by JS `Date.getDay()` (0 = Sunday).
 *  日曜日/月曜日/火曜日/水曜日/木曜日/金曜日/土曜日 ⇒ 日/月/火/水/木/金/土. */
const DOW_KANJI: readonly string[] = ['日', '月', '火', '水', '木', '金', '土'];

/** 32-bit unsigned hash of a string — used only for the fallback pick when
 *  the day-of-week kanji isn't in the bundle. Cheap, stable. Not crypto. */
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

  // Day-of-week kanji — shown even if already mastered, because the
  // "Wednesday → 水" mnemonic is the whole point. We only fall back if
  // this bundle somehow doesn't carry the character.
  const dow = DOW_KANJI[now.getDay()];
  if (dow && allKanji.includes(dow)) {
    await putMeta('kotd', { char: dow, date: today });
    return dow;
  }

  // Fallback: hash the ISO date and pick from unmastered kanji (or any).
  const pool = allKanji.filter((c) => !masteredChars.has(c));
  const source = pool.length > 0 ? pool : allKanji;
  if (source.length === 0) return '';
  const idx = hash32(today) % source.length;
  const char = source[idx];
  await putMeta('kotd', { char, date: today });
  return char;
}
