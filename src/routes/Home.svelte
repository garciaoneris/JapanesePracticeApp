<script lang="ts">
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';

  const b = bundle();
  const kanjiList = $derived(
    Object.values(b.kanji).sort((a, c) => c.jlpt - a.jlpt || a.strokes - c.strokes),
  );
  const counts = $derived({
    kanji: Object.keys(b.kanji).length,
    words: Object.keys(b.words).length,
  });

  let filter = $state<'all' | 5 | 4>('all');
  const filtered = $derived(filter === 'all' ? kanjiList : kanjiList.filter((k) => k.jlpt === filter));
</script>

<header class="hero">
  <div class="hero-inner">
    <p class="kicker">日本語</p>
    <h1>Japanese Practice</h1>
    <p class="muted">{counts.kanji} kanji · {counts.words.toLocaleString()} words · JLPT N5–N4</p>
    <div class="cta-row">
      <a class="cta primary" href="/review" use:link>
        <span class="cta-icon">▶</span>
        <span>Start review</span>
      </a>
    </div>
  </div>
</header>

<section class="kanji-section">
  <div class="section-head">
    <h2>Kanji</h2>
    <div class="filters">
      <button class:active={filter === 'all'} onclick={() => (filter = 'all')}>All</button>
      <button class:active={filter === 5} onclick={() => (filter = 5)}>N5</button>
      <button class:active={filter === 4} onclick={() => (filter = 4)}>N4</button>
    </div>
  </div>

  <div class="grid">
    {#each filtered as k (k.char)}
      <a class="cell" href={`/learn/${encodeURIComponent(k.char)}`} use:link aria-label={k.meanings.join(', ')}>
        <span class="ch">{k.char}</span>
        <span class="lvl">N{k.jlpt}</span>
      </a>
    {/each}
  </div>
</section>

<style>
  .hero {
    padding: 2.5rem 1.25rem 1.5rem;
  }
  .hero-inner {
    text-align: center;
    background: linear-gradient(160deg, rgba(124, 92, 255, 0.18), rgba(255, 122, 89, 0.14));
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 24px;
    padding: 2rem 1.5rem;
    box-shadow: var(--shadow-md);
  }
  .kicker {
    margin: 0;
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.5rem;
    color: var(--accent);
    letter-spacing: 0.2em;
    font-weight: 400;
  }
  .hero h1 {
    margin: 0.4rem 0 0.5rem;
    font-size: clamp(1.8rem, 6vw, 2.4rem);
    font-weight: 700;
    letter-spacing: -0.01em;
    background: linear-gradient(135deg, #fff, #d8d8e8);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .muted {
    color: var(--fg-dim);
    margin: 0 0 1.4rem;
    font-size: 0.95rem;
  }
  .cta-row {
    display: flex;
    justify-content: center;
  }
  .cta {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.85rem 1.7rem;
    border-radius: 14px;
    font-weight: 600;
    font-size: 1rem;
    color: #1b1b1f;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    box-shadow: 0 10px 28px rgba(255, 122, 89, 0.4);
    transition: transform 0.1s;
  }
  .cta:active {
    transform: scale(0.97);
  }
  .cta-icon {
    font-size: 0.85em;
  }

  .kanji-section {
    padding: 0.5rem 1rem 2.5rem;
  }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.85rem;
    padding: 0 0.25rem;
  }
  h2 {
    font-size: 0.85rem;
    color: var(--fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin: 0;
    font-weight: 600;
  }
  .filters {
    display: flex;
    gap: 0.3rem;
  }
  .filters button {
    padding: 0.35rem 0.85rem;
    font-size: 0.8rem;
    border-radius: 999px;
    background: var(--bg-alt);
  }
  .filters button.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #1b1b1f;
    font-weight: 600;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
    gap: 0.5rem;
  }
  .cell {
    aspect-ratio: 1 / 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 14px;
    color: var(--fg);
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    transition: transform 0.12s, border-color 0.12s, background 0.12s;
  }
  .cell:hover {
    border-color: rgba(255, 122, 89, 0.45);
    background: var(--bg-elevated);
  }
  .cell:active {
    transform: scale(0.94);
  }
  .ch { font-size: 2rem; line-height: 1; }
  .lvl {
    font-size: 0.6rem;
    color: var(--fg-dim);
    margin-top: 0.3rem;
    letter-spacing: 0.05em;
  }
</style>
