/** Pub-sub for XP-gain events. `addXp` fires `notifyXpGain`; the global
 *  `<XpToast />` mounted in App.svelte subscribes and renders the float-up
 *  chip. Decouples the XP award plumbing from the UI so any route can
 *  call `addXp()` and get the visual feedback for free.
 *
 *  We also track the last pointer-down position globally so the toast
 *  can anchor its chip to the learner's last tap instead of always
 *  flying up from the corner — the XP award feels tied to the action. */

interface Pointer { x: number; y: number; }

type Listener = (amount: number, pointer: Pointer) => void;

const listeners = new Set<Listener>();

// Default: roughly center of the viewport until we see a real tap.
let lastPointer: Pointer = {
  x: typeof window !== 'undefined' ? window.innerWidth / 2 : 0,
  y: typeof window !== 'undefined' ? window.innerHeight / 2 : 0,
};

if (typeof document !== 'undefined') {
  // Capture-phase so we see every tap before any `e.stopPropagation()`
  // inside the routes. Passive so we don't slow scrolling.
  document.addEventListener(
    'pointerdown',
    (e) => {
      lastPointer = { x: e.clientX, y: e.clientY };
    },
    { passive: true, capture: true },
  );
}

export function getLastPointer(): Pointer {
  return lastPointer;
}

export function onXpGain(cb: Listener): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

export function notifyXpGain(amount: number): void {
  if (!Number.isFinite(amount) || amount <= 0) return;
  const rounded = Math.round(amount);
  const pos = { ...lastPointer };
  for (const l of listeners) {
    try { l(rounded, pos); } catch { /* toast subscriber should never take down the caller */ }
  }
}
