import { getBundle, putBundle } from './db';
import type { Bundle } from './types';

let cached: Bundle | null = null;

export async function ensureBundleLoaded(): Promise<Bundle> {
  if (cached) return cached;

  const stored = await getBundle();
  if (stored) {
    cached = stored;
  } else {
    const url = `${import.meta.env.BASE_URL}data/bundle.json`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`bundle fetch ${res.status}`);
    cached = (await res.json()) as Bundle;
    await putBundle(cached);
  }

  return cached;
}

export function bundle(): Bundle {
  if (!cached) throw new Error('bundle not loaded; call ensureBundleLoaded() first');
  return cached;
}
