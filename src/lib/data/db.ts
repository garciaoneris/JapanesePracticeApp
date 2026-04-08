import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { Bundle, SrsState } from './types';

interface Schema extends DBSchema {
  meta: { key: string; value: unknown };
  bundle: { key: 'bundle'; value: Bundle };
  srs: {
    key: string;
    value: SrsState;
    indexes: { 'by-due': number };
  };
  // Best practice-morph score per kanji; key is the kanji character.
  scores: { key: string; value: number };
}

const DB_NAME = 'jp-practice';
const DB_VERSION = 2;

let _db: Promise<IDBPDatabase<Schema>> | null = null;

export function db(): Promise<IDBPDatabase<Schema>> {
  if (!_db) {
    _db = openDB<Schema>(DB_NAME, DB_VERSION, {
      upgrade(database, oldVersion) {
        if (oldVersion < 1) {
          database.createObjectStore('meta');
          database.createObjectStore('bundle');
          const srs = database.createObjectStore('srs', { keyPath: 'id' });
          srs.createIndex('by-due', 'dueAt');
        }
        if (oldVersion < 2) {
          database.createObjectStore('scores');
        }
      },
    });
  }
  return _db;
}

export async function getBundle(): Promise<Bundle | undefined> {
  const d = await db();
  return d.get('bundle', 'bundle');
}

export async function putBundle(bundle: Bundle): Promise<void> {
  const d = await db();
  await d.put('bundle', bundle, 'bundle');
  await d.put('meta', bundle.version, 'bundle-version');
}

export async function getSrs(id: string): Promise<SrsState | undefined> {
  const d = await db();
  return d.get('srs', id);
}

export async function putSrs(state: SrsState): Promise<void> {
  const d = await db();
  await d.put('srs', state);
}

export async function dueSrs(now: number, limit = 50): Promise<SrsState[]> {
  const d = await db();
  const out: SrsState[] = [];
  const idx = d.transaction('srs').store.index('by-due');
  for await (const cursor of idx.iterate(IDBKeyRange.upperBound(now))) {
    out.push(cursor.value);
    if (out.length >= limit) break;
  }
  return out;
}

export async function getBestScore(char: string): Promise<number | undefined> {
  const d = await db();
  return d.get('scores', char);
}

export async function getAllBestScores(): Promise<Map<string, number>> {
  const d = await db();
  const out = new Map<string, number>();
  let cursor = await d.transaction('scores').store.openCursor();
  while (cursor) {
    out.set(String(cursor.key), cursor.value);
    cursor = await cursor.continue();
  }
  return out;
}

/** Store `score` as the new best for `char` if it beats whatever was there.
 * Returns the resulting best (which may be the old one if it was higher). */
export async function putBestScoreIfBetter(char: string, score: number): Promise<number> {
  const d = await db();
  const tx = d.transaction('scores', 'readwrite');
  const current = (await tx.store.get(char)) ?? -1;
  const next = Math.max(current, score);
  if (next !== current) await tx.store.put(next, char);
  await tx.done;
  return next;
}
