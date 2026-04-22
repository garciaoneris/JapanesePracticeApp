/** Daily-goal tracking. Active-minute accounting is visibility-aware so
 *  an idle tab doesn't inflate a streak. Call startTick() when a Learn or
 *  Review screen mounts and stopTick() in its onDestroy. */

import { getMeta, putMeta } from '../data/db';

export interface GoalState {
  goalMinutes: number;
  todayMinutes: number;
  todayDate: string; // ISO yyyy-mm-dd, local time
}

/** Local ISO date (yyyy-mm-dd). Using local so the user's day boundary
 *  matches their perception; UTC would roll over mid-evening for some. */
export function todayIso(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export async function getGoalState(): Promise<GoalState> {
  const goalMinutes = (await getMeta<number>('dailyGoalMinutes')) ?? 10;
  const today = todayIso();
  const storedDate = (await getMeta<string>('todayDate')) ?? today;
  let todayMinutes = (await getMeta<number>('todayMinutes')) ?? 0;
  if (storedDate !== today) {
    // Day rolled over — reset counter, persist new date.
    todayMinutes = 0;
    await putMeta('todayDate', today);
    await putMeta('todayMinutes', 0);
  }
  return { goalMinutes, todayMinutes, todayDate: today };
}

export async function setGoalMinutes(minutes: number): Promise<void> {
  const m = Math.max(1, Math.min(240, Math.round(minutes)));
  await putMeta('dailyGoalMinutes', m);
}

/** Add N minutes to today's counter. Capped at goal+5 so a user who leaves
 *  a tab open overnight doesn't end up with a 400-minute day. Returns
 *  whether the goal was newly hit on this call (for celebration chaining). */
export async function addMinutes(mins: number): Promise<{ state: GoalState; justHitGoal: boolean }> {
  if (!Number.isFinite(mins) || mins <= 0) {
    return { state: await getGoalState(), justHitGoal: false };
  }
  const before = await getGoalState();
  const cap = before.goalMinutes + 5;
  const next = Math.min(cap, before.todayMinutes + mins);
  await putMeta('todayMinutes', next);
  await putMeta('todayDate', before.todayDate);
  const justHitGoal = before.todayMinutes < before.goalMinutes && next >= before.goalMinutes;
  return { state: { ...before, todayMinutes: next }, justHitGoal };
}

// ── Active-minute ticker ─────────────────────────────────────────────────

/** Tick state shared across callers — only one ticker runs at a time. */
let tickHandle: ReturnType<typeof setInterval> | null = null;
let refCount = 0;
let lastTick = 0;
const TICK_MS = 30_000; // 30s resolution keeps writes light

function onTick(): void {
  if (document.visibilityState !== 'visible') return;
  const now = Date.now();
  // Skip the first tick after visibility flip so we don't credit idle time.
  if (now - lastTick > TICK_MS * 3) {
    lastTick = now;
    return;
  }
  lastTick = now;
  addMinutes(TICK_MS / 60_000).catch(() => {});
}

function onVisibility(): void {
  if (document.visibilityState === 'visible') lastTick = Date.now();
}

export function startTick(): void {
  refCount += 1;
  if (refCount > 1) return;
  lastTick = Date.now();
  document.addEventListener('visibilitychange', onVisibility);
  tickHandle = setInterval(onTick, TICK_MS);
}

export function stopTick(): void {
  refCount = Math.max(0, refCount - 1);
  if (refCount > 0) return;
  if (tickHandle !== null) clearInterval(tickHandle);
  tickHandle = null;
  document.removeEventListener('visibilitychange', onVisibility);
}
