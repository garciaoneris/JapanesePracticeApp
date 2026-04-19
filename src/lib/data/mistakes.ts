/** Track open mistakes the user has made in Vocab quizzes and Review.
 *
 * Stored in IndexedDB `meta` store as an array. Mode-aware keys:
 * `mistakes` in regular mode, `native-mistakes` in native mode — kept
 * separate so Native-mode progress doesn't contaminate the normal flow.
 * Synced via gist so the same mistake list follows the user across devices. */

import { getMeta, putMeta } from './db';
import { isNativeMode } from './mode';

export type MistakeType = 'word-reading' | 'word-meaning' | 'kanji-meaning' | 'kanji-writing';

export interface Mistake {
  /** What kind of question was missed */
  type: MistakeType;
  /** word.id for word types, kanji char for kanji-meaning */
  id: string;
  /** How many times this exact question has been missed */
  count: number;
  /** Consecutive correct answers in Reinforce mode */
  streak: number;
  /** Last time this was missed or correctly reinforced (ms epoch) */
  lastSeen: number;
}

/** Tombstone written when a mistake is cleared (reached the 3-streak
 * threshold in Reinforce). Kept in IndexedDB + synced via gist so a
 * second device that still has the stale active mistake learns that the
 * first device has since resolved it, and doesn't resurrect the mistake
 * on the next pull. Compared via `clearedAt` vs mistake `lastSeen` so a
 * brand-new re-miss (recordMistake updates lastSeen past clearedAt)
 * correctly re-opens the mistake. */
export interface ClearedMistake {
  type: MistakeType;
  id: string;
  clearedAt: number;
}

/** Number of consecutive correct answers required to clear a mistake. */
export const REINFORCE_CLEAR_STREAK = 3;

export async function mistakesKey(): Promise<string> {
  return (await isNativeMode()) ? 'native-mistakes' : 'mistakes';
}

/** IndexedDB meta key for cleared-mistake tombstones in the current mode. */
export async function clearedMistakesKey(): Promise<string> {
  return (await isNativeMode()) ? 'native-mistakes-cleared' : 'mistakes-cleared';
}

export async function getClearedMistakes(): Promise<ClearedMistake[]> {
  return (await getMeta<ClearedMistake[]>(await clearedMistakesKey())) ?? [];
}

export async function getMistakes(): Promise<Mistake[]> {
  return (await getMeta<Mistake[]>(await mistakesKey())) ?? [];
}

export async function getMistakeCount(): Promise<number> {
  return (await getMistakes()).length;
}

/** Lazy sync-push trigger to avoid circular import with sync.ts. */
function pushSync() {
  import('./sync').then((s) => s.schedulePush()).catch(() => {});
}

/** Record a new mistake (or bump count + reset streak on existing one).
 *  Called when the user gets an answer wrong in Vocabulary or Review. */
export async function recordMistake(
  m: Pick<Mistake, 'type' | 'id'>,
): Promise<void> {
  const list = await getMistakes();
  const idx = list.findIndex((x) => x.type === m.type && x.id === m.id);
  const now = Date.now();
  if (idx >= 0) {
    list[idx] = {
      ...list[idx],
      count: list[idx].count + 1,
      streak: 0,
      lastSeen: now,
    };
  } else {
    list.push({ type: m.type, id: m.id, count: 1, streak: 0, lastSeen: now });
  }
  await putMeta(await mistakesKey(), list);
  pushSync();
}

/** Correct answer in Reinforce: bump streak; remove entry when cleared
 * and write a tombstone to the cleared-mistakes list so other devices
 * can tell the resolution apart from a never-synced stale entry. */
export async function reinforceCorrect(type: MistakeType, id: string): Promise<void> {
  const list = await getMistakes();
  const idx = list.findIndex((x) => x.type === type && x.id === id);
  if (idx < 0) return;
  const now = Date.now();
  list[idx].streak += 1;
  list[idx].lastSeen = now;
  if (list[idx].streak >= REINFORCE_CLEAR_STREAK) {
    list.splice(idx, 1);
    // Record tombstone.
    const cleared = await getClearedMistakes();
    const ti = cleared.findIndex((c) => c.type === type && c.id === id);
    if (ti >= 0) {
      cleared[ti].clearedAt = now;  // bump if re-cleared later
    } else {
      cleared.push({ type, id, clearedAt: now });
    }
    await putMeta(await clearedMistakesKey(), cleared);
  }
  await putMeta(await mistakesKey(), list);
  pushSync();
}

/** Wrong answer in Reinforce: reset streak, bump count. */
export async function reinforceWrong(type: MistakeType, id: string): Promise<void> {
  const list = await getMistakes();
  const idx = list.findIndex((x) => x.type === type && x.id === id);
  if (idx < 0) return;
  list[idx].streak = 0;
  list[idx].count += 1;
  list[idx].lastSeen = Date.now();
  await putMeta(await mistakesKey(), list);
  pushSync();
}
