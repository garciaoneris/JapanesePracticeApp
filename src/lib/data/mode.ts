/** Mode-aware score key helpers.
 *
 * Regular mode uses `quiz-scores` / `review-scores`.
 * Native mode uses `native-quiz-scores` / `native-review-scores`.
 * This keeps progress separate so toggling native mode doesn't
 * contaminate regular-mode achievement tracking. */

import { getMeta } from './db';

let _cached: boolean | null = null;

/** Check if native mode is enabled. Caches after first call. */
export async function isNativeMode(): Promise<boolean> {
  if (_cached !== null) return _cached;
  _cached = (await getMeta<boolean>('native-mode')) ?? false;
  return _cached;
}

/** Update the cache when the user toggles the setting. */
export function setNativeModeCache(v: boolean): void {
  _cached = v;
}

/** IndexedDB meta key for vocab quiz scores in the current mode. */
export async function quizScoreKey(): Promise<string> {
  return (await isNativeMode()) ? 'native-quiz-scores' : 'quiz-scores';
}

/** IndexedDB meta key for review scores in the current mode. */
export async function reviewScoreKey(): Promise<string> {
  return (await isNativeMode()) ? 'native-review-scores' : 'review-scores';
}
