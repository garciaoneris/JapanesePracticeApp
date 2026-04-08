/** Map a practice-morph best score to a display color.
 *
 *   100  → gold               (reward for a perfect attempt)
 *    99  → vibrant green
 *     0  → faded muddy yellow
 *
 * Between 0 and 99 we interpolate hue, saturation, and lightness linearly
 * from yellow toward green so small improvements shift the hue visibly.
 *
 * Returns an `hsl(...)` (or hex) string, or `null` for "no score yet".
 */
export function scoreColor(score: number | undefined | null): string | null {
  if (score === undefined || score === null) return null;
  if (score >= 100) return '#ffd24a'; // gold — slightly warmer than pure #ffd700

  const t = Math.max(0, Math.min(99, score)) / 99;

  // Faded yellow → vibrant green.
  const h = 50 + (138 - 50) * t; // 50 = yellow, 138 = green
  const s = 28 + (58 - 28) * t;
  const l = 46 + (54 - 46) * t;

  return `hsl(${h.toFixed(0)}, ${s.toFixed(0)}%, ${l.toFixed(0)}%)`;
}

/** A softer version of the same color suitable for backgrounds (lower alpha). */
export function scoreBg(score: number | undefined | null): string | null {
  if (score === undefined || score === null) return null;
  if (score >= 100) return 'rgba(255, 210, 74, 0.18)';

  const t = Math.max(0, Math.min(99, score)) / 99;
  const h = 50 + (138 - 50) * t;
  const s = 28 + (58 - 28) * t;
  return `hsla(${h.toFixed(0)}, ${s.toFixed(0)}%, 48%, 0.16)`;
}
