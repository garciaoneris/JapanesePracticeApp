<script lang="ts">
  import type { Segment } from '../data/types';
  import { speakJa } from '../speech/tts';

  interface Props {
    segments: Segment[];
    /** Kanji the learner has mastered (score >= 80). Segments whose kanji are
     * all in this set render as plain text; others render with furigana. */
    knownKanji?: ReadonlySet<string>;
    /** The kanji currently being studied is implicitly known even before it
     * reaches the score threshold — otherwise the Learn page would put ruby
     * on its own hero character. */
    currentKanji?: string;
  }
  const { segments, knownKanji, currentKanji }: Props = $props();

  import { onDestroy } from 'svelte';

  // Container ref so we can scope gloss-idx queries to THIS instance.
  let container: HTMLElement;

  // Tooltip state. We keep the anchor rect so the tooltip positions itself
  // directly above whichever word was tapped, with a small gap.
  let openIndex = $state<number | null>(null);
  let tooltipText = $state<string>('');
  let tooltipHue = $state<number>(0);
  let tooltipLeft = $state<number>(0);
  let tooltipTop = $state<number>(0);
  let arrowNudge = $state<number>(0);

  // The tooltip is rendered as a direct child of <body> so it's never
  // clipped or offset by parent transforms (e.g., animated callout cards).
  let tooltipEl: HTMLDivElement | null = null;

  function ensureTooltipEl(): HTMLDivElement {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.setAttribute('role', 'tooltip');
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  function updateTooltipDom() {
    if (openIndex === null || !tooltipText) {
      if (tooltipEl) tooltipEl.style.display = 'none';
      return;
    }
    const el = ensureTooltipEl();
    el.className = 'furigana-tooltip';
    el.textContent = tooltipText;
    el.style.cssText = `
      position: fixed;
      left: ${tooltipLeft}px;
      top: ${tooltipTop}px;
      transform: translate(-50%, calc(-100% - 6px));
      max-width: min(78vw, 360px);
      width: max-content;
      background: var(--bg-elevated, #262633);
      color: var(--fg, #f0f0f5);
      border: 1.5px solid hsl(${tooltipHue}deg, 70%, 55%);
      border-radius: 10px;
      padding: 0.55rem 0.8rem;
      font-size: 0.9rem;
      font-family: -apple-system, 'Inter', system-ui, sans-serif;
      box-shadow: 0 14px 36px rgba(0,0,0,0.5);
      z-index: 10000;
      pointer-events: none;
      text-align: center;
      line-height: 1.3;
      display: block;
    `;
    // Measure and nudge if clipping viewport edges.
    requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      const pad = 8;
      let nudge = 0;
      if (r.left < pad) {
        nudge = pad - r.left;
      } else if (r.right > window.innerWidth - pad) {
        nudge = -(r.right - window.innerWidth + pad);
      }
      if (nudge !== 0) {
        tooltipLeft += nudge;
        el.style.left = `${tooltipLeft}px`;
      }
      arrowNudge = -nudge;
    });
  }

  $effect(() => {
    // Re-run whenever tooltip state changes.
    void openIndex; void tooltipText; void tooltipLeft; void tooltipTop; void tooltipHue;
    updateTooltipDom();
  });

  onDestroy(() => {
    if (tooltipEl) { tooltipEl.remove(); tooltipEl = null; }
  });

  // Deterministic golden-angle hue spacing: 73° gives adjacent segments
  // visibly distinct colors without clashing.
  function hueFor(i: number): number {
    return (i * 73) % 360;
  }

  const CJK_START = 0x4e00;
  const CJK_END = 0x9fff;
  function isKanji(ch: string): boolean {
    const cp = ch.codePointAt(0);
    return cp !== undefined && cp >= CJK_START && cp <= CJK_END;
  }

  /** Does this segment contain any kanji at all? */
  function hasKanji(seg: Segment): boolean {
    for (const c of seg.t) if (isKanji(c)) return true;
    return false;
  }

  /** Are all kanji in this segment "known" (mastered or currently studied)? */
  function allKnown(seg: Segment): boolean {
    for (const c of seg.t) {
      if (!isKanji(c)) continue;
      if (currentKanji && c === currentKanji) continue;
      if (!knownKanji || !knownKanji.has(c)) return false;
    }
    return true;
  }

  /** Decide the rendering mode for a segment. */
  function modeFor(seg: Segment): 'ruby' | 'plain-glossed' | 'plain' {
    if (!hasKanji(seg)) return 'plain';
    const clickable = !!seg.g;
    if (!allKnown(seg)) return 'ruby';
    return clickable ? 'plain-glossed' : 'plain';
  }

  function positionTooltip(target: HTMLElement) {
    const rect = target.getBoundingClientRect();
    tooltipLeft = rect.left + rect.width / 2;
    tooltipTop = rect.top;
  }


  function onWordTap(i: number, seg: Segment, e: Event) {
    // Stop the event from bubbling up to the "speak sentence" container, and
    // block the native default (text-selection / iOS callout menu).
    e.stopPropagation();
    e.preventDefault();
    if (openIndex === i) {
      openIndex = null;
      return;
    }
    const target = e.currentTarget as HTMLElement;
    positionTooltip(target);
    openIndex = i;
    tooltipText = seg.g ?? '';
    tooltipHue = hueFor(i);
    // Speak just the word, not the whole sentence.
    speakJa(seg.t);
  }

  function onKey(i: number, seg: Segment, e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      onWordTap(i, seg, e);
    }
  }

  // Dismiss on any outside click. Attached only while a tooltip is open, and
  // the listener is scheduled on the next tick so the click that opened the
  // tooltip doesn't immediately close it.
  $effect(() => {
    if (openIndex === null) return;
    let handler: (() => void) | null = null;
    const t = window.setTimeout(() => {
      handler = () => { openIndex = null; };
      document.addEventListener('click', handler, { once: true, capture: true });
    }, 0);
    return () => {
      window.clearTimeout(t);
      if (handler) document.removeEventListener('click', handler, { capture: true } as EventListenerOptions);
    };
  });

  // Re-anchor the tooltip on resize/scroll while it's open so it stays
  // glued to its word instead of drifting off-screen.
  function reanchor() {
    if (openIndex === null) return;
    const target = container?.querySelector<HTMLElement>(`[data-gloss-idx="${openIndex}"]`);
    if (target) positionTooltip(target);
  }
  $effect(() => {
    if (openIndex === null) return;
    window.addEventListener('scroll', reanchor, { passive: true });
    window.addEventListener('resize', reanchor);
    return () => {
      window.removeEventListener('scroll', reanchor);
      window.removeEventListener('resize', reanchor);
    };
  });
</script>

<span class="furi-wrap" bind:this={container}><span class="furi">
  {#each segments as seg, i (i)}
    {@const mode = modeFor(seg)}
    {#if mode === 'ruby'}
      <ruby
        class="glossable"
        class:clickable={!!seg.g}
        style="--hue: {hueFor(i)}deg"
        data-gloss-idx={i}
        onclick={seg.g ? (e) => onWordTap(i, seg, e) : undefined}
        onkeydown={seg.g ? (e) => onKey(i, seg, e) : undefined}
        role={seg.g ? 'button' : undefined}
        tabindex={seg.g ? 0 : undefined}
      >
        {seg.t}<rt>{seg.r ?? ''}</rt>
      </ruby>
    {:else if mode === 'plain-glossed'}
      <span
        class="glossable clickable"
        style="--hue: {hueFor(i)}deg"
        data-gloss-idx={i}
        onclick={(e) => onWordTap(i, seg, e)}
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

</span>

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

  /* Every clickable word opts out of native text selection + the iOS
     long-press copy/paste callout so a tap is unambiguously a click. */
  .glossable.clickable {
    cursor: pointer;
    -webkit-user-select: none;
    user-select: none;
    -webkit-touch-callout: none;
    -webkit-tap-highlight-color: transparent;
    border-radius: 2px;
    border-bottom: 2px solid hsla(var(--hue), 70%, 60%, 0.55);
    transition: border-color 0.15s, background 0.15s;
  }
  .glossable.clickable:hover,
  .glossable.clickable:focus-visible {
    border-bottom-color: hsl(var(--hue), 80%, 65%);
    background: hsla(var(--hue), 70%, 55%, 0.14);
    outline: none;
  }
  .plain {
    /* inline, no decoration */
  }

  /* Tooltip styles are now inline (rendered as a body-level DOM node
     in the script block) to avoid parent transform/clip issues. */
</style>
