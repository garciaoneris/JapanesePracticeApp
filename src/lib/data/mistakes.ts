/** Track open mistakes the user has made in Vocab quizzes and Review.
 *
 * Stored in IndexedDB `meta` store as an array. Mode-aware keys:
 * `mistakes` in regular mode, `native-mistakes` in native mode — kept
 * separate so Native-mode progress doesn't contaminate the normal flow.
 * Synced via gist so the same mistake list follows the user across devices. */

import { getMeta, putMeta } from './db';
import { isNativeMode } from './mode';

export type MistakeType = 'word-reading' | 'word-meaning' | 'kanji-meaning';

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

/** Number of consecutive correct answers required to clear a mistake. */
export const REINFORCE_CLEAR_STREAK = 3;

export async function mistakesKey(): Promise<string> {
  return (await isNativeMode()) ? 'native-mistakes' : 'mistakes';
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

/** Correct answer in Reinforce: bump streak; remove entry when cleared. */
export async function reinforceCorrect(type: MistakeType, id: string): Promise<void> {
  const list = await getMistakes();
  const idx = list.findIndex((x) => x.type === type && x.id === id);
  if (idx < 0) return;
  list[idx].streak += 1;
  list[idx].lastSeen = Date.now();
  if (list[idx].streak >= REINFORCE_CLEAR_STREAK) {
    list.splice(idx, 1);
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
