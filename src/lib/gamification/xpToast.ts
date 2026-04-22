/** Pub-sub for XP-gain events. `addXp` fires `notifyXpGain`; the global
 *  `<XpToast />` mounted in App.svelte subscribes and renders the float-up
 *  chip. Decouples the XP award plumbing from the UI so any route can
 *  call `addXp()` and get the visual feedback for free. */

type Listener = (amount: number) => void;

const listeners = new Set<Listener>();

export function onXpGain(cb: Listener): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

export function notifyXpGain(amount: number): void {
  if (!Number.isFinite(amount) || amount <= 0) return;
  const rounded = Math.round(amount);
  for (const l of listeners) {
    try { l(rounded); } catch { /* toast subscriber should never take down the caller */ }
  }
}
