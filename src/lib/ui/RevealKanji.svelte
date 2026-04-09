<script lang="ts">
  import { onMount } from 'svelte';

  interface Props {
    svg: string;
    strokeCount: number;
  }
  const { svg, strokeCount }: Props = $props();

  const VB = 109;

  let host: HTMLDivElement;
  let paths = $state<SVGPathElement[]>([]);
  let revealed = $state(0); // 0 = hidden, 1..N = that many strokes, cycles back to 0

  function cycle() {
    revealed = (revealed + 1) % (strokeCount + 1);
  }

  // Apply opacity per path whenever `revealed` changes. Paths 0..revealed-1
  // become visible, the rest fade out. Using `opacity` (not `display: none`)
  // so they remain in the layout tree for smooth transitions.
  $effect(() => {
    const n = revealed;
    paths.forEach((p, i) => {
      if (i < n) {
        p.setAttribute('stroke', '#ff7a59');
        p.setAttribute('opacity', '0.95');
      } else {
        p.setAttribute('opacity', '0');
      }
    });
  });

  onMount(() => {
    host.innerHTML = svg;
    const svgEl = host.querySelector('svg');
    if (svgEl) {
      svgEl.setAttribute('viewBox', `0 0 ${VB} ${VB}`);
      svgEl.setAttribute('width', '100%');
      svgEl.setAttribute('height', '100%');
    }
    const list = Array.from(host.querySelectorAll('path')) as SVGPathElement[];
    list.forEach((p) => {
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', '#ff7a59');
      p.setAttribute('stroke-width', '3');
      p.setAttribute('stroke-linecap', 'round');
      p.setAttribute('stroke-linejoin', 'round');
      p.setAttribute('opacity', '0');
      p.style.transition = 'opacity 0.25s ease-out';
    });
    paths = list;
  });
</script>

<button class="reveal" onclick={cycle} aria-label="Tap to peek at strokes">
  <div class="stage" bind:this={host}></div>
  {#if revealed === 0}
    <div class="silhouette" aria-hidden="true">?</div>
    <div class="hint">tap to peek</div>
  {:else}
    <div class="counter">{revealed} / {strokeCount}</div>
  {/if}
</button>

<style>
  .reveal {
    position: relative;
    width: clamp(5rem, 18vw, 8rem);
    height: clamp(5rem, 18vw, 8rem);
    padding: 0;
    background: transparent;
    border: 1px dashed rgba(255, 122, 89, 0.35);
    border-radius: 16px;
    cursor: pointer;
    flex-shrink: 0;
    overflow: hidden;
    transition: border-color 0.15s, background 0.15s, transform 0.08s;
  }
  .reveal:hover {
    border-color: rgba(255, 122, 89, 0.65);
    background: rgba(255, 122, 89, 0.06);
  }
  .reveal:active {
    transform: scale(0.97);
  }
  .stage {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .stage :global(svg) {
    width: 100%;
    height: 100%;
  }
  .silhouette {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 3.5rem;
    color: rgba(255, 122, 89, 0.35);
    font-weight: 700;
    pointer-events: none;
  }
  .hint {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0.3rem;
    font-size: 0.65rem;
    text-align: center;
    color: var(--fg-dim);
    letter-spacing: 0.03em;
    pointer-events: none;
  }
  .counter {
    position: absolute;
    right: 0.4rem;
    bottom: 0.3rem;
    font-size: 0.65rem;
    font-weight: 700;
    color: var(--accent);
    background: rgba(0, 0, 0, 0.45);
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;
    pointer-events: none;
  }
</style>
