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
    border: 1.5px solid rgba(230, 160, 40, 0.7);
    /* Drop-shadow intentionally omitted — on a grid of 500+ tiles
       (L3 filter) every shadow was its own compositor layer. A
       stronger border gets the same "this tile is special" read
       without the per-tile paint cost. */
  }
  .tile.tier-platinum {
    background: var(--tile-platinum);
    /* --ink goes dark on Washi/Sakura (readable over the pastel lilac
       gradient) and near-white on Neon (readable over the dark
       semi-transparent platinum layer). */
    color: var(--ink);
    border: 1.5px solid rgba(120, 100, 200, 0.7);
    /* Same perf note as .tier-gold. */
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
    /* Was `rgba(255,255,255,0.5) + backdrop-filter: blur(4px)`. At 500+
       tiles on the L3 filter that was 500+ live blur filters the iPad
       compositor had to maintain — the #1 source of scroll jank.
       A solid semi-transparent fill gets the same "floating chip"
       look with zero compositor cost. */
    background: rgba(255, 255, 255, 0.82);
    color: inherit;
    line-height: 1.2;
    z-index: 1;
  }
  :global([data-theme='neon']) .score {
    background: rgba(0, 0, 0, 0.55);
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
