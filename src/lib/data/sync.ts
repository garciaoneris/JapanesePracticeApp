import { db, getMeta, putMeta, deleteMeta, getAllBestScores } from './db';
import type { SrsState, Attempt } from './types';

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
  /** Per-kanji vocabulary quiz best scores (0-100%). Added after initial
   *  release so older payloads may not have this field. */
  quizScores?: Record<string, number>;
  /** Per-kanji SRS review best scores (0-100%). */
  reviewScores?: Record<string, number>;
  /** Whether native mode is enabled (all kanji treated as mastered). */
  nativeMode?: boolean;
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

  // Quiz scores (vocabulary quiz best % per kanji)
  const quizScores = (await getMeta<Record<string, number>>('quiz-scores')) ?? {};

  // Review scores (SRS review best % per kanji)
  const reviewScores = (await getMeta<Record<string, number>>('review-scores')) ?? {};

  // Native mode flag
  const nativeMode = (await getMeta<boolean>('native-mode')) ?? false;

  return { v: 1, ts: Date.now(), scores, srs, attempts, quizScores, reviewScores, nativeMode };
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

  // ---- Merge native mode flag ----
  if (remote.nativeMode !== undefined) {
    const localNative = (await getMeta<boolean>('native-mode')) ?? false;
    if (remote.nativeMode && !localNative) {
      await putMeta('native-mode', true);
      modified = true;
    }
  }

  return modified;
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
