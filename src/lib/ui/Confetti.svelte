<script lang="ts">
  interface Props {
    count?: number;
  }
  let { count = 26 }: Props = $props();

  /** Colors rotate through the theme accents + mints + skies so the confetti
   *  re-themes automatically when the user switches palette. */
  const COLORS = [
    'var(--accent)',
    'var(--accent-2)',
    'var(--mint)',
    'var(--sky)',
    'var(--rose)',
  ];

  // Deterministic-ish layout — seeded by index, not Math.random, so a reduced-
  // motion user who never sees the fall still gets sensible static dots.
  function rnd(i: number, salt: number): number {
    const h = Math.sin(i * 9301 + salt * 49297) * 233280;
    return h - Math.floor(h);
  }

  const pieces = Array.from({ length: count }, (_, i) => ({
    left: `${rnd(i, 1) * 100}%`,
    bg: COLORS[i % COLORS.length],
    delay: rnd(i, 2) * 1.5,
    duration: 2.5 + rnd(i, 3) * 2,
    size: 6 + rnd(i, 4) * 8,
    rot: rnd(i, 5) * 360,
  }));
</script>

<div class="confetti" aria-hidden="true">
  {#each pieces as p, i (i)}
    <div
      class="piece"
      style="left: {p.left}; width: {p.size}px; height: {p.size * 1.6}px; background: {p.bg}; animation-delay: {p.delay}s; animation-duration: {p.duration}s; transform: rotate({p.rot}deg);"
    ></div>
  {/each}
</div>

<style>
  .confetti {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
  }
  .piece {
    position: absolute;
    top: -20px;
    border-radius: 2px;
  }
  @media (prefers-reduced-motion: no-preference) {
    .piece {
      animation-name: confetti-fall;
      animation-timing-function: linear;
      animation-iteration-count: infinite;
    }
  }
</style>
