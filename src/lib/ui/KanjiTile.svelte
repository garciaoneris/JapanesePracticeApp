<script lang="ts">
  export type TileTier =
    | 'new'       // never practiced
    | 'progress'  // attempted, score < 80
    | 'green'     // stroke ≥ 80 (mastered)
    | 'gold-edge' // stroke ≥ 85, no perfect quiz/review
    | 'gold'      // stroke ≥ 85 + perfect quiz OR review
    | 'platinum'  // stroke ≥ 85 + perfect quiz AND review
    | 'review';   // outstanding review mistake

  interface Props {
    char: string;
    reading?: string;
    score?: number | null;
    tier: TileTier;
    size?: number;
  }
  let { char, reading = '', score = null, tier, size = 82 }: Props = $props();

  const glyphSize = $derived(size * 0.45);
</script>

<div class={`tile tier-${tier}`} style="width: {size}px; height: {size}px;">
  <div class="glyph jp-serif" style="font-size: {glyphSize}px;">{char}</div>
  {#if reading}
    <div class="reading jp-sans">{reading}</div>
  {/if}
  {#if score !== null && score !== undefined}
    <div class="score tnum">{score}</div>
  {/if}
  {#if tier === 'new'}
    <div class="new-dot" aria-hidden="true"></div>
  {/if}
</div>

<style>
  .tile {
    position: relative;
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    cursor: pointer;
    color: var(--ink);
    background: var(--surface);
    border: 1.5px dashed var(--border-strong);
  }
  .tile.tier-progress {
    background: var(--surface-2);
    border: 1.5px solid var(--border-strong);
  }
  .tile.tier-green {
    background: var(--tile-mastered);
    border: 1.5px solid color-mix(in oklab, var(--mint) 60%, transparent);
  }
  .tile.tier-gold-edge {
    background: var(--surface);
    border: 2px solid #E6A33D;
  }
  .tile.tier-gold {
    background: var(--tile-gold);
    color: #3A2810;
    border: 1.5px solid rgba(230, 160, 40, 0.5);
    box-shadow:
      0 6px 16px rgba(230, 160, 40, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.5);
  }
  .tile.tier-platinum {
    background: var(--tile-platinum);
    /* --ink goes dark on Washi/Sakura (readable over the pastel lilac
       gradient) and near-white on Neon (readable over the dark
       semi-transparent platinum layer). Hardcoding a dark purple here
       left Neon platinum glyphs almost invisible. */
    color: var(--ink);
    border: 1.5px solid rgba(120, 100, 200, 0.5);
    box-shadow:
      0 6px 18px rgba(124, 92, 255, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.8);
  }
  .tile.tier-review {
    background: color-mix(in oklab, var(--rose) 12%, var(--surface));
    border: 1.5px solid color-mix(in oklab, var(--rose) 55%, transparent);
  }
  .glyph {
    /* `position: relative` promotes the glyph into the positioned-siblings
       paint layer so it lands *on top of* the absolutely-positioned
       .shimmer-overlay (platinum tier). Without this, the shimmer wash
       would paint over the character itself. */
    position: relative;
    line-height: 1;
    font-weight: 500;
  }
  .reading {
    position: relative;
    font-size: 10px;
    margin-top: 4px;
    opacity: 0.75;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 0 4px;
  }
  .score {
    position: absolute;
    top: 4px;
    right: 4px;
    font-size: 9px;
    font-weight: 800;
    padding: 2px 5px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.5);
    color: inherit;
    backdrop-filter: blur(4px);
    line-height: 1.2;
    /* Explicit z-index keeps the score badge above the shimmer overlay;
       both are absolutely positioned so DOM order alone isn't enough. */
    z-index: 1;
  }
  :global([data-theme='neon']) .score {
    background: rgba(0, 0, 0, 0.35);
    color: #fff;
  }
  .new-dot {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: var(--accent);
  }
</style>
