import { getBundle, putBundle } from './db';
import type { Bundle } from './types';

// Bump this when the on-the-wire shape changes so old IndexedDB caches refetch.
// Must match the `version` field emitted by tools/build_bundle.py.
const EXPECTED_VERSION = '6';

let cached: Bundle | null = null;

async function fetchFresh(): Promise<Bundle> {
  const url = `${import.meta.env.BASE_URL}data/bundle.json?v=${EXPECTED_VERSION}`;
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`bundle fetch ${res.status}`);
  const fresh = (await res.json()) as Bundle;
  await putBundle(fresh);
  return fresh;
}

export async function ensureBundleLoaded(): Promise<Bundle> {
  if (cached && cached.version === EXPECTED_VERSION) return cached;

  const stored = await getBundle();
  if (stored && stored.version === EXPECTED_VERSION) {
    cached = stored;
  } else {
    cached = await fetchFresh();
  }

  return cached;
}

export function bundle(): Bundle {
  if (!cached) throw new Error('bundle not loaded; call ensureBundleLoaded() first');
  return cached;
}
