import { db, getMeta, putMeta, deleteMeta, getAllBestScores } from './db';
import type { SrsState, Attempt } from './types';
import type { Mistake, ClearedMistake } from './mistakes';

// ── Constants ────────────────────────────────────────────────────────────

const GH_API = 'https://api.github.com';
const GIST_FILENAME = 'jp-practice-sync.json';

// ── Sync payload schema ──────────────────────────────────────────────────

export interface SyncPayload {
  v: 1;
  ts: number;
  scores: Record<string, number>;
  srs: SrsState[];
  attempts: Array<Omit<Attempt, 'id'>>;
  /** Per-kanji vocabulary quiz best scores (0-100%). */
  quizScores?: Record<string, number>;
  /** Per-kanji SRS review best scores (0-100%). */
  reviewScores?: Record<string, number>;
  /** Native-mode quiz scores (separate from regular). */
  nativeQuizScores?: Record<string, number>;
  /** Native-mode review scores (separate from regular). */
  nativeReviewScores?: Record<string, number>;
  /** Per-kanji review-drawing best scores (regular mode). */
  reviewDrawScores?: Record<string, number>;
  /** Per-kanji review-drawing best scores (native mode). */
  nativeReviewDrawScores?: Record<string, number>;
  /** Per-kanji fill-in-the-blank (sentence drill) best scores, regular mode. */
  fillKanjiScores?: Record<string, number>;
  /** Per-kanji fill-in-the-blank scores, native mode. */
  nativeFillKanjiScores?: Record<string, number>;
  /** Whether native mode is enabled (all kanji treated as mastered). */
  nativeMode?: boolean;
  /** Open mistakes the user hasn't yet reinforced to clearance (regular mode). */
  mistakes?: Mistake[];
  /** Open mistakes in native mode (tracked separately). */
  nativeMistakes?: Mistake[];
  /** Tombstones for mistakes cleared via Reinforce (regular). Prevents
   *  a second device's stale active-mistake list from resurrecting
   *  already-resolved mistakes after the user fixes them on device A. */
  mistakesCleared?: ClearedMistake[];
  /** Cleared-mistake tombstones, native mode. */
  nativeMistakesCleared?: ClearedMistake[];
}

// ── Token management ─────────────────────────────────────────────────────

export async function getToken(): Promise<string | null> {
  const token = await getMeta<string>('gh-token');
  return token ?? null;
}

export async function setToken(token: string): Promise<void> {
  await putMeta('gh-token', token);
}

export async function clearToken(): Promise<void> {
  await deleteMeta('gh-token');
  await deleteMeta('gh-gist-id');
}

// ── GitHub helpers ───────────────────────────────────────────────────────

function ghHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

async function ghFetch(token: string, path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${GH_API}${path}`, {
    ...init,
    headers: { ...ghHeaders(token), ...(init?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`GitHub API ${res.status}: ${body}`);
  }
  return res;
}

// ── Gist operations ──────────────────────────────────────────────────────

export async function findOrCreateGist(token: string): Promise<string> {
  // Check cached gist ID first.
  const cached = await getMeta<string>('gh-gist-id');
  if (cached) {
    // Verify the gist still exists (a single lightweight GET).
    try {
      await ghFetch(token, `/gists/${cached}`);
      return cached;
    } catch {
      // Cached ID is stale; fall through to search.
      await deleteMeta('gh-gist-id');
    }
  }

  // Search existing gists for one containing our sync file.
  const res = await ghFetch(token, '/gists?per_page=100');
  const gists: Array<{ id: string; files: Record<string, unknown> }> = await res.json();

  for (const gist of gists) {
    if (GIST_FILENAME in gist.files) {
      await putMeta('gh-gist-id', gist.id);
      return gist.id;
    }
  }

  // None found -- create a new private gist with empty initial data.
  const emptyPayload: SyncPayload = { v: 1, ts: 0, scores: {}, srs: [], attempts: [] };
  const createRes = await ghFetch(token, '/gists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      description: 'Japanese Practice PWA sync data',
      public: false,
      files: { [GIST_FILENAME]: { content: JSON.stringify(emptyPayload) } },
    }),
  });
  const created: { id: string } = await createRes.json();
  await putMeta('gh-gist-id', created.id);
  return created.id;
}

// ── Data serialization ───────────────────────────────────────────────────

export async function collectLocal(): Promise<SyncPayload> {
  const d = await db();

  // Scores
  const scoresMap = await getAllBestScores();
  const scores: Record<string, number> = {};
  for (const [k, v] of scoresMap) {
    scores[k] = v;
  }

  // SRS states
  const srs: SrsState[] = [];
  const srsTx = d.transaction('srs', 'readonly');
  let srsCursor = await srsTx.store.openCursor();
  while (srsCursor) {
    srs.push(srsCursor.value);
    srsCursor = await srsCursor.continue();
  }

  // Attempts (strip local-only `id`)
  const attempts: Array<Omit<Attempt, 'id'>> = [];
  const attTx = d.transaction('attempts', 'readonly');
  let attCursor = await attTx.store.openCursor();
  while (attCursor) {
    const { id: _id, ...rest } = attCursor.value;
    attempts.push(rest);
    attCursor = await attCursor.continue();
  }

  // Quiz scores — regular + native mode (stored separately)
  const quizScores = (await getMeta<Record<string, number>>('quiz-scores')) ?? {};
  const nativeQuizScores = (await getMeta<Record<string, number>>('native-quiz-scores')) ?? {};

  // Review scores — regular + native mode (stored separately)
  const reviewScores = (await getMeta<Record<string, number>>('review-scores')) ?? {};
  const nativeReviewScores = (await getMeta<Record<string, number>>('native-review-scores')) ?? {};

  // Review draw scores — regular + native mode
  const reviewDrawScores = (await getMeta<Record<string, number>>('review-draw-scores')) ?? {};
  const nativeReviewDrawScores = (await getMeta<Record<string, number>>('native-review-draw-scores')) ?? {};

  // Fill-kanji (sentence drill) scores — regular + native mode
  const fillKanjiScores = (await getMeta<Record<string, number>>('fill-kanji-scores')) ?? {};
  const nativeFillKanjiScores = (await getMeta<Record<string, number>>('native-fill-kanji-scores')) ?? {};

  // Native mode flag
  const nativeMode = (await getMeta<boolean>('native-mode')) ?? false;

  // Open mistakes — regular + native (tracked separately, same as scores)
  const mistakes = (await getMeta<Mistake[]>('mistakes')) ?? [];
  const nativeMistakes = (await getMeta<Mistake[]>('native-mistakes')) ?? [];

  // Cleared-mistake tombstones — regular + native (paired with the mistakes
  // lists so pullFromGist can distinguish "cleared on the other device"
  // from "never existed on this device").
  const mistakesCleared = (await getMeta<ClearedMistake[]>('mistakes-cleared')) ?? [];
  const nativeMistakesCleared = (await getMeta<ClearedMistake[]>('native-mistakes-cleared')) ?? [];

  return {
    v: 1, ts: Date.now(), scores, srs, attempts,
    quizScores, reviewScores, nativeQuizScores, nativeReviewScores, nativeMode,
    mistakes, nativeMistakes,
    mistakesCleared, nativeMistakesCleared,
    reviewDrawScores, nativeReviewDrawScores,
    fillKanjiScores, nativeFillKanjiScores,
  };
}

// ── Push ─────────────────────────────────────────────────────────────────

export async function pushToGist(token: string, gistId: string): Promise<void> {
  const payload = await collectLocal();
  await ghFetch(token, `/gists/${gistId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: { [GIST_FILENAME]: { content: JSON.stringify(payload) } },
    }),
  });
}

// ── Pull + merge ─────────────────────────────────────────────────────────

export async function pullFromGist(token: string, gistId: string): Promise<boolean> {
  const res = await ghFetch(token, `/gists/${gistId}`);
  const gist: { files: Record<string, { content: string }> } = await res.json();

  const file = gist.files[GIST_FILENAME];
  if (!file?.content) return false;

  const remote: SyncPayload = JSON.parse(file.content);
  if (remote.v !== 1) return false;

  const d = await db();
  let modified = false;

  // ---- Merge scores ----
  {
    const tx = d.transaction('scores', 'readwrite');
    for (const [char, remoteScore] of Object.entries(remote.scores)) {
      const local = await tx.store.get(char);
      if (local === undefined || remoteScore > local) {
        await tx.store.put(remoteScore, char);
        modified = true;
      }
    }
    await tx.done;
  }

  // ---- Merge SRS ----
  {
    const tx = d.transaction('srs', 'readwrite');
    for (const remoteSrs of remote.srs) {
      const local = await tx.store.get(remoteSrs.id);
      if (!local) {
        await tx.store.put(remoteSrs);
        modified = true;
      } else if (
        remoteSrs.reps > local.reps ||
        (remoteSrs.reps === local.reps && remoteSrs.dueAt > local.dueAt)
      ) {
        await tx.store.put(remoteSrs);
        modified = true;
      }
    }
    await tx.done;
  }

  // ---- Merge attempts ----
  {
    const tx = d.transaction('attempts', 'readwrite');
    const idx = tx.store.index('by-char-time');
    for (const remoteAttempt of remote.attempts) {
      const key: [string, number] = [remoteAttempt.char, remoteAttempt.ts];
      const existing = await idx.get(key);
      if (!existing) {
        await tx.store.add(remoteAttempt as Attempt);
        modified = true;
      }
    }
    await tx.done;
  }

  // ---- Merge quiz scores (max wins) ----
  if (remote.quizScores) {
    const local = (await getMeta<Record<string, number>>('quiz-scores')) ?? {};
    let quizModified = false;
    for (const [char, remoteScore] of Object.entries(remote.quizScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        quizModified = true;
      }
    }
    if (quizModified) {
      await putMeta('quiz-scores', local);
      modified = true;
    }
  }

  // ---- Merge review scores (max wins) ----
  if (remote.reviewScores) {
    const local = (await getMeta<Record<string, number>>('review-scores')) ?? {};
    let revModified = false;
    for (const [char, remoteScore] of Object.entries(remote.reviewScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        revModified = true;
      }
    }
    if (revModified) {
      await putMeta('review-scores', local);
      modified = true;
    }
  }

  // ---- Merge review draw scores (max wins) ----
  if (remote.reviewDrawScores) {
    const local = (await getMeta<Record<string, number>>('review-draw-scores')) ?? {};
    let rdModified = false;
    for (const [char, remoteScore] of Object.entries(remote.reviewDrawScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        rdModified = true;
      }
    }
    if (rdModified) { await putMeta('review-draw-scores', local); modified = true; }
  }

  // ---- Merge native quiz scores (max wins) ----
  if (remote.nativeQuizScores) {
    const local = (await getMeta<Record<string, number>>('native-quiz-scores')) ?? {};
    let nqModified = false;
    for (const [char, remoteScore] of Object.entries(remote.nativeQuizScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        nqModified = true;
      }
    }
    if (nqModified) { await putMeta('native-quiz-scores', local); modified = true; }
  }

  // ---- Merge native review scores (max wins) ----
  if (remote.nativeReviewScores) {
    const local = (await getMeta<Record<string, number>>('native-review-scores')) ?? {};
    let nrModified = false;
    for (const [char, remoteScore] of Object.entries(remote.nativeReviewScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        nrModified = true;
      }
    }
    if (nrModified) { await putMeta('native-review-scores', local); modified = true; }
  }

  // ---- Merge native review draw scores (max wins) ----
  if (remote.nativeReviewDrawScores) {
    const local = (await getMeta<Record<string, number>>('native-review-draw-scores')) ?? {};
    let nrdModified = false;
    for (const [char, remoteScore] of Object.entries(remote.nativeReviewDrawScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        nrdModified = true;
      }
    }
    if (nrdModified) { await putMeta('native-review-draw-scores', local); modified = true; }
  }

  // ---- Merge fill-kanji scores (regular + native, max wins) ----
  if (remote.fillKanjiScores) {
    const local = (await getMeta<Record<string, number>>('fill-kanji-scores')) ?? {};
    let fkModified = false;
    for (const [char, remoteScore] of Object.entries(remote.fillKanjiScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        fkModified = true;
      }
    }
    if (fkModified) { await putMeta('fill-kanji-scores', local); modified = true; }
  }
  if (remote.nativeFillKanjiScores) {
    const local = (await getMeta<Record<string, number>>('native-fill-kanji-scores')) ?? {};
    let nfkModified = false;
    for (const [char, remoteScore] of Object.entries(remote.nativeFillKanjiScores)) {
      if (remoteScore > (local[char] ?? 0)) {
        local[char] = remoteScore;
        nfkModified = true;
      }
    }
    if (nfkModified) { await putMeta('native-fill-kanji-scores', local); modified = true; }
  }

  // ---- Merge native mode flag ----
  if (remote.nativeMode !== undefined) {
    const localNative = (await getMeta<boolean>('native-mode')) ?? false;
    if (remote.nativeMode && !localNative) {
      await putMeta('native-mode', true);
      modified = true;
    }
  }

  // ---- Merge cleared-mistake tombstones FIRST (needed for active merge) --
  // Tombstones are a union keyed by `${type}:${id}` with max `clearedAt`.
  const mergedCleared = await mergeClearedMistakes(
    'mistakes-cleared', remote.mistakesCleared ?? [],
  );
  if (mergedCleared.changed) modified = true;
  const mergedNativeCleared = await mergeClearedMistakes(
    'native-mistakes-cleared', remote.nativeMistakesCleared ?? [],
  );
  if (mergedNativeCleared.changed) modified = true;

  // ---- Merge open mistakes, honoring tombstones ----
  if (remote.mistakes) {
    if (await mergeMistakes('mistakes', remote.mistakes, mergedCleared.list)) modified = true;
  }
  if (remote.nativeMistakes) {
    if (await mergeMistakes('native-mistakes', remote.nativeMistakes, mergedNativeCleared.list)) modified = true;
  }

  return modified;
}

/** Merge a remote cleared-mistakes tombstone list into the local one.
 *  Tombstones are keyed by type+id; on conflict we keep the MAX clearedAt
 *  (more recent clearing wins). Returns the merged list so the subsequent
 *  active-mistakes merge can reference it. */
async function mergeClearedMistakes(
  key: string, remote: ClearedMistake[],
): Promise<{ list: ClearedMistake[]; changed: boolean }> {
  const local = (await getMeta<ClearedMistake[]>(key)) ?? [];
  const index = new Map<string, ClearedMistake>();
  for (const c of local) index.set(`${c.type}:${c.id}`, c);
  let changed = false;
  for (const rc of remote) {
    const k = `${rc.type}:${rc.id}`;
    const lc = index.get(k);
    if (!lc) {
      index.set(k, { ...rc });
      changed = true;
    } else if (rc.clearedAt > lc.clearedAt) {
      index.set(k, { ...rc });
      changed = true;
    }
  }
  const list = [...index.values()];
  if (changed) await putMeta(key, list);
  return { list, changed };
}

/** Merge a remote mistakes list into the local one.
 *
 *  Strategy: union by `${type}:${id}`. For conflicts, take max of
 *  count/streak/lastSeen (more progress wins). Then DROP any entry
 *  whose `lastSeen` is at-or-before the corresponding cleared-tombstone
 *  `clearedAt` — that means the other device has since resolved the
 *  mistake, so we shouldn't resurrect it even if remote's stale payload
 *  still contains it. If a later re-miss has bumped lastSeen past
 *  clearedAt, the tombstone no longer applies and the mistake is active
 *  again. */
async function mergeMistakes(
  key: string, remote: Mistake[], cleared: ClearedMistake[],
): Promise<boolean> {
  const local = (await getMeta<Mistake[]>(key)) ?? [];
  const clearedByKey = new Map<string, number>();
  for (const c of cleared) clearedByKey.set(`${c.type}:${c.id}`, c.clearedAt);

  const index = new Map<string, Mistake>();
  for (const m of local) index.set(`${m.type}:${m.id}`, m);
  for (const rm of remote) {
    const k = `${rm.type}:${rm.id}`;
    const lm = index.get(k);
    if (!lm) {
      index.set(k, { ...rm });
    } else {
      index.set(k, {
        type: rm.type,
        id: rm.id,
        count: Math.max(lm.count, rm.count),
        streak: Math.max(lm.streak, rm.streak),
        lastSeen: Math.max(lm.lastSeen, rm.lastSeen),
      });
    }
  }

  // Apply tombstones: drop any active entry whose most-recent activity
  // is older than the tombstone (i.e. cleared after last miss).
  const merged: Mistake[] = [];
  for (const [k, m] of index) {
    const clearedAt = clearedByKey.get(k) ?? 0;
    if (m.lastSeen > clearedAt) merged.push(m);
  }

  // Detect change: signatures of (id, type, count, streak, lastSeen).
  const sigOf = (ms: Mistake[]) => ms
    .map((m) => `${m.type}:${m.id}:${m.count}:${m.streak}:${m.lastSeen}`)
    .sort()
    .join('|');
  if (sigOf(local) === sigOf(merged)) return false;
  await putMeta(key, merged);
  return true;
}

// ── Orchestration ────────────────────────────────────────────────────────

export async function syncNow(): Promise<{ ok: boolean; error?: string }> {
  try {
    const token = await getToken();
    if (!token) return { ok: false, error: 'No GitHub token configured' };

    const gistId = await findOrCreateGist(token);
    await pullFromGist(token, gistId);
    await pushToGist(token, gistId);
    await putMeta('last-sync', Date.now());
    return { ok: true };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: message };
  }
}

export async function getLastSync(): Promise<number | null> {
  const ts = await getMeta<number>('last-sync');
  return ts ?? null;
}

// ── Auto-push (debounced) ────────────────────────────────────────────────

let pushTimer: ReturnType<typeof setTimeout> | null = null;

export function schedulePush(): void {
  if (pushTimer !== null) {
    clearTimeout(pushTimer);
  }

  pushTimer = setTimeout(() => {
    pushTimer = null;

    void (async () => {
      try {
        const token = await getToken();
        if (!token) return;

        const gistId = await getMeta<string>('gh-gist-id');
        if (!gistId) return;

        await pushToGist(token, gistId);
      } catch {
        // Fire-and-forget: swallow errors from background push.
      }
    })();
  }, 2000);
}
