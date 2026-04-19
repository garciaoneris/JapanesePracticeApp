/** Furigana display preference.
 *
 * The Furigana component renders ruby text over kanji segments. How
 * aggressively it does so is user-configurable:
 *
 *  - 'always'        : ruby on every kanji (default; maximum reference).
 *  - 'hide-mastered' : hide ruby on segments whose kanji are all
 *                      score >= 80 (same threshold as the kanji grid's
 *                      "mastered" state). Good for weaning off furigana.
 *  - 'never'         : no ruby ever (pure-Japanese reading test).
 *
 * The value is stored in IndexedDB meta store under 'furigana-mode' and
 * synced through the gist payload. A module-level cache + subscriber
 * list lets the Furigana component react to changes without a full
 * reload. Loaded once on app startup (App.svelte) so the first render
 * already reflects the persisted preference.
 */

import { getMeta, putMeta } from './db';

export type FuriganaMode = 'always' | 'hide-mastered' | 'never';

export const FURIGANA_MODE_KEY = 'furigana-mode';
const DEFAULT_MODE: FuriganaMode = 'always';

let cached: FuriganaMode = DEFAULT_MODE;
const subscribers = new Set<(m: FuriganaMode) => void>();

export async function loadFuriganaMode(): Promise<FuriganaMode> {
  const stored = await getMeta<FuriganaMode>(FURIGANA_MODE_KEY);
  cached = stored && (stored === 'always' || stored === 'hide-mastered' || stored === 'never')
    ? stored
    : DEFAULT_MODE;
  return cached;
}

export function getFuriganaMode(): FuriganaMode {
  return cached;
}

export async function setFuriganaMode(m: FuriganaMode): Promise<void> {
  if (m === cached) return;
  cached = m;
  await putMeta(FURIGANA_MODE_KEY, m);
  for (const cb of subscribers) cb(m);
}

/** Update the in-memory cache from a pulled sync payload without writing
 *  back to IndexedDB (sync.ts handles that to avoid a write-write loop). */
export function setFuriganaModeCache(m: FuriganaMode): void {
  if (m === cached) return;
  cached = m;
  for (const cb of subscribers) cb(m);
}

/** Subscribe for changes. Returns an unsubscribe function. */
export function subscribeFuriganaMode(cb: (m: FuriganaMode) => void): () => void {
  subscribers.add(cb);
  return () => subscribers.delete(cb);
}
