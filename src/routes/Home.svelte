<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { getAllBestScores, getMeta } from '../lib/data/db';
  import { scoreBg, scoreColor } from '../lib/score/color';
  import { quizScoreKey, reviewScoreKey } from '../lib/data/mode';

  const b = bundle();
  // Progressive curriculum order. Primary key is JLPT level descending so N5
  // (5) comes first and ungraded (0) comes last. Within a level we tiebreak
  // on school grade ascending (1=elementary kyouiku, 8=general jouyou,
  // 9–10=jinmeiyou) then stroke count ascending. `grade === 0` gets pushed
  // to the end of its level with a sentinel of 99.
  const kanjiList = $derived(
    Object.values(b.kanji).sort((a, c) => {
      if (c.jlpt !== a.jlpt) return c.jlpt - a.jlpt;
      const ag = a.grade || 99;
      const cg = c.grade || 99;
      if (ag !== cg) return ag - cg;
      return a.strokes - c.strokes;
    }),
  );
  const counts = $derived({
    kanji: Object.keys(b.kanji).length,
    words: Object.keys(b.words).length,
  });

  type JlptFilter = 'all' | 5 | 4 | 3 | 2 | 1 | 0;
  const FILTER_KEY = 'home-jlpt-filter';
  function loadFilter(): JlptFilter {
    const v = sessionStorage.getItem(FILTER_KEY);
    if (v === 'all') return 'all';
    const n = Number(v);
    if ([0, 1, 2, 3, 4, 5].includes(n)) return n as JlptFilter;
    return 'all';
  }
  let filter = $state<JlptFilter>(loadFilter());
  $effect(() => { sessionStorage.setItem(FILTER_KEY, String(filter)); });
  const filtered = $derived(filter === 'all' ? kanjiList : kanjiList.filter((k) => k.jlpt === filter));

  // Map of kanji char → best score (0-100). Loaded once on mount — svelte-spa-router
  // re-mounts Home on every navigation back, so this is always fresh.
  let bestScores = $state<Map<string, number>>(new Map());
  let quizScores = $state<Map<string, number>>(new Map());
  let reviewScores = $state<Map<string, number>>(new Map());
  // "Mastered" = the known-kanji threshold used by filtering and the Vocabulary
  // tab (>= 80). "Gold" = the new reward tier (>= 85).
  let masteredCount = $derived(
    [...bestScores.values()].filter((v) => v >= 80).length,
  );
  let goldCount = $derived([...bestScores.values()].filter((v) => v >= 85).length);

  onMount(async () => {
    bestScores = await getAllBestScores();
    const [qk, rk] = await Promise.all([quizScoreKey(), reviewScoreKey()]);
    const [qs, rs] = await Promise.all([
      getMeta<Record<string, number>>(qk),
      getMeta<Record<string, number>>(rk),
    ]);
    if (qs) quizScores = new Map(Object.entries(qs));
    if (rs) reviewScores = new Map(Object.entries(rs));
  });

  function cellStyle(char: string): string {
    const s = bestScores.get(char);
    if (s === undefined) return '';
    const border = scoreColor(s);
    const bg = scoreBg(s);
    return `border-color: ${border}; background: ${bg};`;
  }

  function badgeStyle(char: string): string {
    const s = bestScores.get(char);
    if (s === undefined) return '';
    const c = scoreColor(s);
    return `color: ${c}; border-color: ${c};`;
  }

  /** Primary reading for the cell label: prefer on'yomi (the standard
   * dictionary reading learners associate with each kanji), fall back to
   * kun'yomi. On'yomi are stored in katakana by KANJIDIC2 so we convert
   * to hiragana for a uniform display. Strips okurigana markers (".") and
   * prefix/suffix dashes so "の.む" → "のむ", "-び" → "び". */
  function primaryReading(kun: string[], on: string[]): string {
    const clean = (s: string) => s.replace(/[.\-]/g, '').trim();
    const toHira = (s: string) =>
      [...s].map((c) => {
        const cp = c.codePointAt(0)!;
        return cp >= 0x30a1 && cp <= 0x30f6 ? String.fromCodePoint(cp - 0x60) : c;
      }).join('');
    for (const r of on) {
      const c = clean(r);
      if (c) return toHira(c);
    }
    for (const r of kun) {
      const c = clean(r);
      if (c) return c;
    }
    return '';
  }

  function badgeTier(char: string): 'none' | 'green' | 'gold' | 'red' | 'shiny-gold' | 'shiny-platinum' {
    const stroke = bestScores.get(char) ?? 0;
    const quiz = quizScores.get(char) ?? -1;   // -1 = never quizzed
    const review = reviewScores.get(char) ?? -1;

    if (stroke < 80) return 'none';

    // Check for review mistakes (review score > 0 but < 100)
    if (review >= 0 && review < 100) return 'red';

    const perfectQuiz = quiz === 100;
    const perfectReview = review === 100;

    if (perfectQuiz && perfectReview) return 'shiny-platinum';
    if (perfectQuiz || perfectReview) return 'shiny-gold';
    if (stroke >= 85) return 'gold';
    return 'green';
  }
</script>

<header class="hero">
  <a class="settings-gear" href="/settings" use:link aria-label="Settings">⚙</a>
  <div class="hero-inner">
    <p class="kicker">日本語</p>
    <h1>Japanese Practice</h1>
    <p class="muted">
      {counts.kanji} kanji · {counts.words.toLocaleString()} words · JLPT N5–N1
      {#if bestScores.size > 0}
        <br />
        <span class="progress-line">
          ✓ {masteredCount} mastered · {goldCount} gold · {bestScores.size} attempted
        </span>
      {/if}
    </p>
    <div class="cta-row">
      <a class="cta primary" href="/review" use:link>
        <span class="cta-icon">▶</span>
        <span>Review{filter !== 'all' ? ` ${filter === 0 ? '—' : `N${filter}`}` : ''}</span>
      </a>
      <a class="cta secondary" href="/vocabulary" use:link>
        <span class="cta-icon">📘</span>
        <span>Vocabulary</span>
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
      <button class:active={filter === 3} onclick={() => (filter = 3)}>N3</button>
      <button class:active={filter === 2} onclick={() => (filter = 2)}>N2</button>
      <button class:active={filter === 1} onclick={() => (filter = 1)}>N1</button>
      <button class:active={filter === 0} onclick={() => (filter = 0)} title="Jouyou / jinmeiyou kanji without a JLPT tag">—</button>
    </div>
  </div>

  <div class="grid">
    {#each filtered as k (k.char)}
      <a
        class="cell"
        class:green={badgeTier(k.char) === 'green'}
        class:gold={badgeTier(k.char) === 'gold'}
        class:red={badgeTier(k.char) === 'red'}
        class:shiny-gold={badgeTier(k.char) === 'shiny-gold'}
        class:shiny-platinum={badgeTier(k.char) === 'shiny-platinum'}
        href={`/learn/${encodeURIComponent(k.char)}`}
        use:link
        aria-label={k.meanings.join(', ')}
        style={cellStyle(k.char)}
      >
        <span class="ch">{k.char}</span>
        <span class="lvl">{primaryReading(k.kun, k.on)}</span>
        {#if bestScores.has(k.char)}
          <span class="score-badge" style={badgeStyle(k.char)}>{bestScores.get(k.char)}</span>
        {/if}
      </a>
    {/each}
  </div>
</section>

<style>
  .hero {
    padding: 2.5rem 1.25rem 1.5rem;
    position: relative;
  }
  .settings-gear {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    font-size: 1.4rem;
    color: var(--fg-dim);
    opacity: 0.6;
    text-decoration: none;
    transition: opacity 0.15s;
    z-index: 1;
  }
  .settings-gear:hover {
    opacity: 1;
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
    line-height: 1.5;
  }
  .progress-line {
    display: inline-block;
    margin-top: 0.3rem;
    color: var(--fg);
    font-variant-numeric: tabular-nums;
  }
  .cta-row {
    display: flex;
    justify-content: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .cta {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.85rem 1.5rem;
    border-radius: 14px;
    font-weight: 600;
    font-size: 0.95rem;
    color: #1b1b1f;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    box-shadow: 0 10px 28px rgba(255, 122, 89, 0.4);
    transition: transform 0.1s;
  }
  .cta.secondary {
    background: linear-gradient(135deg, var(--indigo), #5a3cf0);
    color: #fff;
    box-shadow: 0 10px 28px rgba(124, 92, 255, 0.4);
  }
  .cta:active {
    transform: scale(0.97);
  }
  .cta-icon {
    font-size: 0.95em;
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
    position: relative;
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
    transition: transform 0.12s, border-color 0.12s, background 0.12s, box-shadow 0.2s;
  }
  .cell:hover {
    background: var(--bg-elevated);
  }
  .cell:active {
    transform: scale(0.94);
  }
  .cell.green {
    border-color: var(--ok);
    background: rgba(94, 202, 124, 0.1);
  }
  .cell.gold {
    box-shadow: 0 0 0 2px rgba(255, 210, 74, 0.4), 0 8px 22px rgba(255, 210, 74, 0.2);
  }
  .cell.red {
    border-color: var(--err);
    background: rgba(255, 107, 107, 0.1);
  }
  .cell.shiny-gold {
    border-color: #ffd24a;
    animation: shimmer-gold 2s ease-in-out infinite;
  }
  .cell.shiny-platinum {
    border-color: #e5e4e2;
    animation: shimmer-plat 2s ease-in-out infinite;
  }
  @keyframes shimmer-gold {
    0%, 100% { box-shadow: 0 0 0 2px #ffd24a, 0 0 8px rgba(255,210,74,0.3); }
    50% { box-shadow: 0 0 0 2px #ffd24a, 0 0 18px rgba(255,210,74,0.6); }
  }
  @keyframes shimmer-plat {
    0%, 100% { box-shadow: 0 0 0 2px #e5e4e2, 0 0 8px rgba(229,228,226,0.3); }
    50% { box-shadow: 0 0 0 2px #e5e4e2, 0 0 18px rgba(229,228,226,0.6); }
  }
  .ch { font-size: 1.9rem; line-height: 1; }
  .lvl {
    font-size: 0.72rem;
    color: var(--fg-dim);
    margin-top: 0.35rem;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
    letter-spacing: 0.02em;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 0 0.25rem;
  }
  .score-badge {
    position: absolute;
    top: 4px;
    right: 4px;
    font-family: -apple-system, 'Inter', system-ui, sans-serif;
    font-size: 0.62rem;
    font-weight: 700;
    padding: 0.1rem 0.35rem;
    border-radius: 999px;
    border: 1px solid currentColor;
    background: rgba(0, 0, 0, 0.45);
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
    letter-spacing: 0.02em;
  }
</style>
