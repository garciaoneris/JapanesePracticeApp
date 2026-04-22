/** Display-name preference. Shown in the Home greeting "おかえり, {name}".
 *  Empty string means the greeting collapses to just "おかえり". */

import { getMeta, putMeta } from '../data/db';

export async function getDisplayName(): Promise<string> {
  return (await getMeta<string>('displayName')) ?? '';
}

export async function setDisplayName(name: string): Promise<void> {
  const trimmed = name.trim().slice(0, 40);
  await putMeta('displayName', trimmed);
}
