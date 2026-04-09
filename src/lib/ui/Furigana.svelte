<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Segment } from '../data/types';

  interface Props {
    segments: Segment[];
  }
  const { segments }: Props = $props();

  // At most one tooltip open at a time. openIndex tracks which segment owns it.
  let openIndex = $state<number | null>(null);
  let tooltipText = $state<string>('');
  let tooltipHue = $state<number>(0);

  // Deterministic golden-angle hue spacing: 73° is close enough to 137.5° mod 360
  // to give adjacent segments visibly distinct colors without clashing.
  function hueFor(i: number): number {
    return (i * 73) % 360;
  }

  function toggle(i: number, seg: Segment, e: MouseEvent | KeyboardEvent) {
    e.stopPropagation();
    if (openIndex === i) {
      openIndex = null;
      return;
    }
    openIndex = i;
    tooltipText = seg.g ?? '';
    tooltipHue = hueFor(i);
  }

  function onKey(i: number, seg: Segment, e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle(i, seg, e);
    }
  }

  function closeAll() {
    openIndex = null;
  }

  // Global click handler to dismiss when tapping outside a glossed span.
  function onDocClick() {
    if (openIndex !== null) openIndex = null;
  }

  $effect(() => {
    if (openIndex !== null) {
      // Defer to next tick so the click that opened it doesn't immediately close it.
      const handler = () => closeAll();
      setTimeout(() => document.addEventListener('click', handler, { once: true }), 0);
      return () => document.removeEventListener('click', handler);
    }
  });

  onDestroy(() => {
    openIndex = null;
  });
</script>

<span class="furi">
  {#each segments as seg, i (i)}
    {#if seg.r && seg.g}
      <ruby
        class="glossed"
        style="--hue: {hueFor(i)}deg"
        onclick={(e) => toggle(i, seg, e)}
        onkeydown={(e) => onKey(i, seg, e)}
        role="button"
        tabindex="0"
      >
        {seg.t}<rt>{seg.r}</rt>
      </ruby>
    {:else if seg.r}
      <ruby>{seg.t}<rt>{seg.r}</rt></ruby>
    {:else if seg.g}
      <span
        class="glossed"
        style="--hue: {hueFor(i)}deg"
        onclick={(e) => toggle(i, seg, e)}
        onkeydown={(e) => onKey(i, seg, e)}
        role="button"
        tabindex="0"
      >
        {seg.t}
      </span>
    {:else}
      <span class="plain">{seg.t}</span>
    {/if}
  {/each}
</span>

{#if openIndex !== null && tooltipText}
  <div class="tooltip" style="--hue: {tooltipHue}deg">{tooltipText}</div>
{/if}

<style>
  .furi {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    line-height: 2.4;
  }
  ruby {
    ruby-position: over;
  }
  rt {
    font-size: 0.55em;
    color: var(--accent);
    font-weight: 500;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
    letter-spacing: 0.02em;
  }
  .glossed {
    cursor: pointer;
    border-bottom: 2px solid hsla(var(--hue), 70%, 60%, 0.55);
    transition: border-color 0.15s, background 0.15s;
    border-radius: 2px;
  }
  .glossed:hover,
  .glossed:focus-visible {
    border-bottom-color: hsl(var(--hue), 80%, 65%);
    background: hsla(var(--hue), 70%, 55%, 0.12);
    outline: none;
  }
  .plain {
    /* inline, no extra styling */
  }

  .tooltip {
    position: fixed;
    left: 50%;
    bottom: 22vh;
    transform: translateX(-50%);
    max-width: min(86vw, 420px);
    background: var(--bg-elevated);
    color: var(--fg);
    border: 1.5px solid hsl(var(--hue), 70%, 55%);
    border-radius: 12px;
    padding: 0.75rem 1rem;
    font-size: 0.95rem;
    font-family: -apple-system, 'Inter', system-ui, sans-serif;
    box-shadow: 0 20px 48px rgba(0, 0, 0, 0.5);
    z-index: 1000;
    animation: tt-in 0.15s ease-out;
    pointer-events: none;
  }
  @keyframes tt-in {
    from { opacity: 0; transform: translate(-50%, 6px); }
    to { opacity: 1; transform: translate(-50%, 0); }
  }
</style>
