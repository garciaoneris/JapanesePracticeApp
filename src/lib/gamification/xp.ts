/** XP + level bookkeeping. Persisted via meta keys 'xp' and 'level'.
 *  Thresholds are triangular so early levels are quick and late ones feel
 *  like real achievements. */

import { getMeta, putMeta } from '../data/db';
import { notifyXpGain } from './xpToast';

/** Cumulative XP required to reach the START of level n (n >= 1).
 *  Level 1 starts at 0 XP; level 2 at 200; level 14 at 21,000. */
export function xpForLevel(n: number): number {
  if (n <= 1) return 0;
  // Sum of 200*(k) for k in 1..n-1  ==  200 * (n-1) * n / 2.
  // Keeps the "level 1 → 200, level 14 → 21000" shape from the spec.
  return 200 * ((n - 1) * n) / 2;
}

/** Resolve the level a given total-XP falls into. */
export function levelForXp(xp: number): number {
  if (xp <= 0) return 1;
  let n = 1;
  while (xpForLevel(n + 1) <= xp) n += 1;
  return n;
}

export interface XpState {
  xp: number;
  level: number;
  /** XP accumulated since the start of the current level. */
  intoLevel: number;
  /** XP required to go from current level to next. */
  levelSpan: number;
}

export async function getXpState(): Promise<XpState> {
  const xp = (await getMeta<number>('xp')) ?? 0;
  const level = levelForXp(xp);
  const base = xpForLevel(level);
  const next = xpForLevel(level + 1);
  return { xp, level, intoLevel: xp - base, levelSpan: next - base };
}

/** Add XP. Returns the new state and whether a level-up happened (for the
 *  celebration trigger in Complete). */
export async function addXp(delta: number): Promise<{ state: XpState; leveledUp: boolean; from?: number; to?: number }> {
  if (!Number.isFinite(delta) || delta <= 0) {
    return { state: await getXpState(), leveledUp: false };
  }
  const prev = (await getMeta<number>('xp')) ?? 0;
  const prevLevel = levelForXp(prev);
  const rounded = Math.round(delta);
  const next = prev + rounded;
  await putMeta('xp', next);
  const nextLevel = levelForXp(next);
  if (nextLevel !== prevLevel) await putMeta('level', nextLevel);
  // Surface the gain to the global <XpToast /> so the learner sees a
  // floating "+N XP" chip per award — drives visibility of the reward
  // loop without each caller having to worry about UI.
  notifyXpGain(rounded);
  const state = await getXpState();
  return nextLevel > prevLevel
    ? { state, leveledUp: true, from: prevLevel, to: nextLevel }
    : { state, leveledUp: false };
}
