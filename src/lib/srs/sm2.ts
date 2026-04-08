import type { Grade, SrsState } from '../data/types';

const DAY_MS = 24 * 60 * 60 * 1000;

export function newCard(id: string, kind: 'kanji' | 'word', now = Date.now()): SrsState {
  return { id, kind, ease: 2.5, intervalDays: 0, dueAt: now, reps: 0, lapses: 0 };
}

export function grade(state: SrsState, g: Grade, now = Date.now()): SrsState {
  let { ease, intervalDays, reps, lapses } = state;

  switch (g) {
    case 'again':
      intervalDays = 0;
      ease = Math.max(1.3, ease - 0.2);
      lapses += 1;
      reps = 0;
      break;
    case 'hard':
      intervalDays = Math.max(1, intervalDays * 1.2);
      ease = Math.max(1.3, ease - 0.15);
      reps += 1;
      break;
    case 'good':
      intervalDays = reps === 0 ? 1 : Math.max(1, intervalDays * ease);
      reps += 1;
      break;
    case 'easy':
      intervalDays = reps === 0 ? 3 : Math.max(1, intervalDays * ease * 1.3);
      ease = ease + 0.15;
      reps += 1;
      break;
  }

  // Short relapse step: due in ~1 minute so user re-sees it this session.
  const dueAt = intervalDays === 0 ? now + 60 * 1000 : now + intervalDays * DAY_MS;

  return { ...state, ease, intervalDays, reps, lapses, dueAt };
}
