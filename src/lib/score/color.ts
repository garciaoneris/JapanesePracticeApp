/** Map a practice-morph best score to a display color.
 *
 *   85-100 → gold               (reward tier — reachable with careful strokes)
 *   60-84  → amber fading to green
 *    0-59  → faded muddy yellow
 *
 * The underlying morph scoring is intentionally generous above 85 since
 * reaching 100 on a freehand iPad canvas is essentially impossible — gold
 * should feel earned, not unreachable.
 *
 * Returns an `hsl(...)` (or hex) string, or `null` for "no score yet".
 */
export function scoreColor(score: number | undefined | null): string | null {
  if (score === undefined || score === null) return null;

  if (score >= 85) return '#ffd24a'; // gold

  if (score >= 60) {
    // Amber (35°) → green (138°) sweep across the 60..84 "competent" range.
    const t = (score - 60) / (84 - 60);
    const h = 35 + (138 - 35) * t;
    const s = 60;
    const l = 50;
    return `hsl(${h.toFixed(0)}, ${s}%, ${l}%)`;
  }

  // Below 60: faded muddy yellow, lighter as you approach 60.
  const t = Math.max(0, score) / 60;
  const h = 50;
  const s = 20 + (40 - 20) * t;
  const l = 42 + (50 - 42) * t;
  return `hsl(${h.toFixed(0)}, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
}

/** A softer version of the same color suitable for backgrounds (lower alpha). */
export function scoreBg(score: number | undefined | null): string | null {
  if (score === undefined || score === null) return null;
  if (score >= 85) return 'rgba(255, 210, 74, 0.18)';

  if (score >= 60) {
    const t = (score - 60) / (84 - 60);
    const h = 35 + (138 - 35) * t;
    return `hsla(${h.toFixed(0)}, 60%, 48%, 0.16)`;
  }

  const t = Math.max(0, score) / 60;
  const s = 20 + (40 - 20) * t;
  return `hsla(50, ${s.toFixed(0)}%, 48%, 0.12)`;
}
