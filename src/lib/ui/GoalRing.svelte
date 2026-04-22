<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    /** 0..1 — progress fraction. Values >1 are clamped to 1. */
    pct: number;
    size?: number;
    stroke?: number;
    /** Centered primary label — usually a number. */
    label?: Snippet;
    /** Small caps sub-label below the main label. */
    sublabel?: string;
  }
  let { pct, size = 112, stroke = 10, label, sublabel }: Props = $props();

  const r = $derived((size - stroke) / 2);
  const c = $derived(2 * Math.PI * r);
  const clamped = $derived(Math.max(0, Math.min(1, pct)));
  const dashOffset = $derived(c * (1 - clamped));

  // Unique gradient id per instance to avoid SVG defs collisions when
  // multiple rings coexist on one page (e.g. Complete's stat grid).
  const gid = `ring-grad-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="ring" style="width: {size}px; height: {size}px;">
  <svg width={size} height={size} aria-hidden="true">
    <defs>
      <linearGradient id={gid} x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stop-color="var(--accent)" />
        <stop offset="1" stop-color="var(--accent-2)" />
      </linearGradient>
    </defs>
    <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--ring-track)" stroke-width={stroke} />
    <circle
      class="progress"
      cx={size / 2}
      cy={size / 2}
      r={r}
      fill="none"
      stroke={`url(#${gid})`}
      stroke-width={stroke}
      stroke-linecap="round"
      stroke-dasharray={c}
      stroke-dashoffset={dashOffset}
    />
  </svg>
  <div class="center">
    {#if label}
      <div class="lbl tnum" style="font-size: {size * 0.26}px;">
        {@render label()}
      </div>
    {/if}
    {#if sublabel}
      <div class="sub">{sublabel}</div>
    {/if}
  </div>
</div>

<style>
  .ring {
    position: relative;
    flex-shrink: 0;
  }
  svg {
    transform: rotate(-90deg);
  }
  .progress {
    /* Transition removed — snaps to target. */
  }
  .center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: inherit;
  }
  .lbl {
    font-weight: 800;
    color: var(--ink);
    line-height: 1;
  }
  .sub {
    font-size: 10px;
    color: var(--muted);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
  }
</style>
