<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { loadKnownKanji } from '../lib/data/known';
  import type { Word } from '../lib/data/types';

  // Loaded asynchronously from IndexedDB; until it resolves we have an empty
  // set, which just means "Ready" is empty and "Almost" is empty too — the
  // empty-state copy covers both cases.
  let knownKanji = $state<Set<string>>(new Set());
  onMount(async () => {
    knownKanji = await loadKnownKanji();
  });

  // Precompute word → [kanji]. Kana-only words are excluded from both lists
  // (they're "free" and not really unlockable vocabulary in the same sense).
  const allWords = $derived(Object.values(bundle().words));

  const ready = $derived.by<Word[]>(() => {
    if (knownKanji.size === 0) return [];
    const out: Word[] = [];
    for (const w of allWords) {
      if (w.kanji.length === 0) continue;
      if (w.kanji.every((c) => knownKanji.has(c))) out.push(w);
    }
    // Prefer shorter compounds first, then shorter readings.
    out.sort(
      (a, b) =>
        a.kanji.length - b.kanji.length ||
        [...a.jp].length - [...b.jp].length ||
        a.reading.length - b.reading.length,
    );
    return out;
  });

  interface AlmostWord {
    word: Word;
    missing: string;
  }

  const almost = $derived.by<AlmostWord[]>(() => {
    if (knownKanji.size === 0) return [];
    const out: AlmostWord[] = [];
    for (const w of allWords) {
      if (w.kanji.length < 2) continue;
      const missing = w.kanji.filter((c) => !knownKanji.has(c));
      if (missing.length === 1) out.push({ word: w, missing: missing[0] });
    }
    out.sort(
      (a, b) =>
        a.word.kanji.length - b.word.kanji.length ||
        [...a.word.jp].length - [...b.word.jp].length,
    );
    return out.slice(0, 60); // cap the "Almost" list — it balloons fast
  });

  function highlightMissing(jp: string, missing: string): { text: string; hi: boolean }[] {
    const out: { text: string; hi: boolean }[] = [];
    for (const ch of jp) {
      out.push({ text: ch, hi: ch === missing });
    }
    return out;
  }
</script>

<a class="back" href="/" use:link>← Back</a>

<header class="head">
  <h1>Vocabulary</h1>
  <p class="subtitle">
    <b>{ready.length}</b> words you can read
    {#if almost.length > 0}
      · <b>{almost.length}</b> one kanji away
    {/if}
  </p>
</header>

{#if ready.length === 0 && almost.length === 0}
  <div class="empty">
    <p>Master some kanji (score ≥ 80) and words will unlock here.</p>
    <a class="cta" href="/" use:link>Go practice kanji</a>
  </div>
{:else}
  {#if ready.length > 0}
    <section>
      <h2>Ready</h2>
      <div class="grid">
        {#each ready as w (w.id)}
          <a class="card ready" href={`/vocab/${encodeURIComponent(w.id)}`} use:link>
            <div class="w-jp">{w.jp}</div>
            <div class="w-reading">{w.reading}</div>
            <div class="w-en">{w.meanings[0] ?? ''}</div>
          </a>
        {/each}
      </div>
    </section>
  {/if}

  {#if almost.length > 0}
    <section>
      <h2>
        Almost <span class="sub">· tap the missing kanji to practice it</span>
      </h2>
      <div class="grid">
        {#each almost as { word, missing } (word.id)}
          <a
            class="card almost"
            href={`/learn/${encodeURIComponent(missing)}`}
            use:link
            aria-label={`Practice ${missing} to unlock ${word.jp}`}
          >
            <div class="w-jp">
              {#each highlightMissing(word.jp, missing) as part}
                <span class:hi={part.hi}>{part.text}</span>
              {/each}
            </div>
            <div class="w-reading">{word.reading}</div>
            <div class="w-en">{word.meanings[0] ?? ''}</div>
          </a>
        {/each}
      </div>
    </section>
  {/if}
{/if}

<style>
  .back {
    display: inline-block;
    padding: 0.75rem 1rem;
    color: var(--fg-dim);
    font-size: 0.9rem;
  }
  .head {
    padding: 0.5rem 1rem 1rem;
    text-align: center;
  }
  .head h1 {
    margin: 0 0 0.3rem;
    font-size: 1.8rem;
    letter-spacing: -0.01em;
  }
  .subtitle {
    margin: 0;
    color: var(--fg-dim);
    font-size: 0.95rem;
  }
  .subtitle b {
    color: var(--fg);
    font-variant-numeric: tabular-nums;
  }
  .empty {
    text-align: center;
    padding: 3rem 1.5rem;
    color: var(--fg-dim);
  }
  .empty .cta {
    display: inline-block;
    margin-top: 1rem;
    padding: 0.75rem 1.4rem;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    color: #1b1b1f;
    font-weight: 600;
  }

  section {
    padding: 0.5rem 1rem 1.5rem;
  }
  h2 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--fg-dim);
    margin: 0 0 0.85rem;
    font-weight: 600;
  }
  .sub {
    text-transform: none;
    letter-spacing: 0;
    font-weight: 400;
    opacity: 0.7;
    font-size: 0.75rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 0.6rem;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.85rem 0.9rem;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--fg);
    transition: border-color 0.15s, transform 0.1s, background 0.15s;
  }
  .card:hover {
    border-color: rgba(255, 122, 89, 0.45);
    background: var(--bg-elevated);
  }
  .card:active {
    transform: scale(0.97);
  }
  .card.ready {
    border-color: rgba(94, 202, 124, 0.25);
  }
  .card.almost {
    opacity: 0.62;
    filter: saturate(0.7);
  }
  .w-jp {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 1.4rem;
    line-height: 1.1;
  }
  .w-jp .hi {
    color: var(--accent);
    font-weight: 700;
  }
  .w-reading {
    color: var(--fg-dim);
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }
  .w-en {
    color: var(--fg);
    font-size: 0.82rem;
    margin-top: 0.25rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
