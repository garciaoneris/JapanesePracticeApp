/** Day-streak bookkeeping. A streak is a run of consecutive days on which
 *  the user met their daily goal. Breaks when a day passes without hitting
 *  the goal. */

import { getMeta, putMeta } from '../data/db';
import { todayIso } from './goal';

export interface StreakState {
  streakDays: number;
  lastActiveDate: string | null;
}

export async function getStreakState(): Promise<StreakState> {
  const streakDays = (await getMeta<number>('streakDays')) ?? 0;
  const lastActiveDate = (await getMeta<string>('lastActiveDate')) ?? null;
  // Gap check: if lastActive is neither today nor yesterday, the streak is
  // cold — reset to zero on read so the UI reflects reality without waiting
  // for the next goal hit.
  if (lastActiveDate) {
    const today = todayIso();
    const y = new Date();
    y.setDate(y.getDate() - 1);
    const yesterday = todayIso(y);
    if (lastActiveDate !== today && lastActiveDate !== yesterday && streakDays > 0) {
      await putMeta('streakDays', 0);
      return { streakDays: 0, lastActiveDate };
    }
  }
  return { streakDays, lastActiveDate };
}

/** Call after `addMinutes` returns `justHitGoal: true`. Idempotent — calling
 *  twice on the same day is a no-op. Returns whether a milestone was crossed
 *  (3/7/30 days) so the caller can fire badge celebrations. */
export async function onGoalHit(): Promise<{ state: StreakState; milestone: 3 | 7 | 30 | null }> {
  const today = todayIso();
  const last = (await getMeta<string>('lastActiveDate')) ?? null;
  if (last === today) {
    const streakDays = (await getMeta<number>('streakDays')) ?? 0;
    return { state: { streakDays, lastActiveDate: today }, milestone: null };
  }
  const yDate = new Date();
  yDate.setDate(yDate.getDate() - 1);
  const yesterday = todayIso(yDate);
  const prev = (await getMeta<number>('streakDays')) ?? 0;
  const next = last === yesterday ? prev + 1 : 1;
  await putMeta('streakDays', next);
  await putMeta('lastActiveDate', today);
  const milestone: 3 | 7 | 30 | null =
    next === 3 ? 3 : next === 7 ? 7 : next === 30 ? 30 : null;
  return { state: { streakDays: next, lastActiveDate: today }, milestone };
}
