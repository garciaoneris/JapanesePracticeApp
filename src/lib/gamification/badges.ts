/** Badge catalog + earn checks. Persisted to meta 'badges' as string[]. */

import { getMeta, putMeta } from '../data/db';

export type BadgeId = 'first_bloom' | 'flow_state' | 'steady_rhythm' | 'plum_blossom';

export interface BadgeDef {
  id: BadgeId;
  title: string;
  criteria: string;
}

export const BADGES: readonly BadgeDef[] = [
  { id: 'first_bloom',    title: 'First Bloom',    criteria: 'Complete 10 reviews in one session' },
  { id: 'flow_state',     title: 'Flow State',     criteria: '7 correct in a row in a review session' },
  { id: 'steady_rhythm',  title: 'Steady Rhythm',  criteria: 'Hit your daily goal 7 days in a row' },
  { id: 'plum_blossom',   title: 'Plum Blossom',   criteria: 'Maintain a 30-day streak' },
];

export async function getEarnedBadges(): Promise<BadgeId[]> {
  const list = (await getMeta<string[]>('badges')) ?? [];
  return list.filter((id): id is BadgeId =>
    BADGES.some((b) => b.id === id),
  );
}

/** Record a newly-earned badge. Idempotent. Returns the badge def if this
 *  was a first-time earn (caller uses this to show the celebration), or
 *  `null` if already owned. */
export async function earn(id: BadgeId): Promise<BadgeDef | null> {
  const owned = await getEarnedBadges();
  if (owned.includes(id)) return null;
  const next = [...owned, id];
  await putMeta('badges', next);
  return BADGES.find((b) => b.id === id) ?? null;
}

/** Event-driven badge checks — caller passes a snapshot of relevant state
 *  and gets back the ids to award. */
export interface BadgeCheckInput {
  sessionReviews?: number;       // reviews completed in current session
  sessionBestStreak?: number;    // longest correct-in-a-row this session
  streakDays?: number;           // overall day streak
}

export function newlyEarnedFromEvent(input: BadgeCheckInput): BadgeId[] {
  const out: BadgeId[] = [];
  if ((input.sessionReviews ?? 0) >= 10) out.push('first_bloom');
  if ((input.sessionBestStreak ?? 0) >= 7) out.push('flow_state');
  if ((input.streakDays ?? 0) >= 7) out.push('steady_rhythm');
  if ((input.streakDays ?? 0) >= 30) out.push('plum_blossom');
  return out;
}
