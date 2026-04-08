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
</script>

<header>
  <h1>Japanese Practice</h1>
  <p class="muted">{counts.kanji} kanji · {counts.words} words · JLPT N5–N4</p>
  <nav>
    <a class="btn primary" href="/review" use:link>Start review</a>
  </nav>
</header>

<section>
  <h2>Kanji</h2>
  <div class="grid">
    {#each kanjiList as k (k.char)}
      <a class="cell" href={`/learn/${encodeURIComponent(k.char)}`} use:link aria-label={k.meanings.join(', ')}>
        <span class="ch">{k.char}</span>
        <span class="lvl">N{k.jlpt}</span>
      </a>
    {/each}
  </div>
</section>

<style>
  header {
    padding: 1.5rem 1rem 0.5rem;
    text-align: center;
  }
  header h1 { margin: 0; font-size: 1.6rem; }
  .muted { color: var(--fg-dim); margin: 0.25rem 0 1rem; }
  .btn { display: inline-block; padding: 0.7em 1.4em; border-radius: 10px; }
  .btn.primary { background: var(--accent); color: #1b1b1f; font-weight: 600; }
  section { padding: 1rem; }
  h2 { font-size: 1rem; color: var(--fg-dim); text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 0.75rem; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(70px, 1fr));
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
    border-radius: 10px;
    color: var(--fg);
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
  }
  .ch { font-size: 1.9rem; line-height: 1; }
  .lvl { font-size: 0.65rem; color: var(--fg-dim); margin-top: 0.25rem; }
</style>
