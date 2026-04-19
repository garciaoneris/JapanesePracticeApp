<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import Furigana from '../lib/ui/Furigana.svelte';
  import { bundle } from '../lib/data/bundle';
  import { fillKanjiScoreKey } from '../lib/data/mode';
  import { getMeta, putMeta } from '../lib/data/db';
  import { recordMistake } from '../lib/data/mistakes';
  import { speakJa } from '../lib/speech/tts';
  import { exampleJp } from '../lib/data/types';
  import type { Kanji, Example } from '../lib/data/types';

  // ── Level handling (mirrors Home.svelte) ───────────────────────────────
  // Levels: 1=N5, 2=N4, 3=N3+N2, 4=N1, 5=ungraded jouyou/jinmeiyou.
  const LEVEL_JLPT: Record<number, number[]> = {
    1: [5], 2: [4], 3: [3, 2], 4: [1], 5: [0],
  };
  function loadFilter(): 'all' | 1 | 2 | 3 | 4 | 5 {
    const v = sessionStorage.getItem('home-jlpt-filter');
    if (v === 'all') return 'all';
    const n = Number(v);
    return ([1, 2, 3, 4, 5] as const).find((x) => x === n) ?? 'all';
  }
  const filter = loadFilter();

  // ── Question building ─────────────────────────────────────────────────

  interface Question {
    /** The kanji the user is being asked to write. */
    kanji: Kanji;
    /** Example containing this kanji (picked once, kept for consistency). */
    example: Example;
    /** Zero-based char index of the first occurrence of `kanji.char` in the
     *  reconstructed sentence string. */
    blankIndex: number;
    /** Pre-reconstructed sentence string (matches segs concat). */
    sentence: string;
    /** Word whose example we picked from (for the English hint + speaking). */
    wordJp: string;
  }

  const b = bundle();
  // Restrict to kanji actually at the current level. In 'all' mode, any
  // kanji is fair game.
  const levelKanjiSet = $derived.by<Set<string>>(() => {
    if (filter === 'all') return new Set(Object.keys(b.kanji));
    const wanted = LEVEL_JLPT[filter] ?? [];
    return new Set(
      Object.values(b.kanji)
        .filter((k) => wanted.includes(k.jlpt))
        .map((k) => k.char),
    );
  });

  /** Pre-index: kanji char → list of (word, example, blankIndex) triples.
   *  Built once; picking a random question is then constant-time. */
  type Triple = { wordJp: string; example: Example; blankIndex: number; sentence: string };
  const index = $derived.by<Map<string, Triple[]>>(() => {
    const out = new Map<string, Triple[]>();
    for (const w of Object.values(b.words)) {
      if (!w.examples || w.examples.length === 0) continue;
      for (const ex of w.examples) {
        const sentence = exampleJp(ex);
        if (!sentence) continue;
        // Collect distinct in-level kanji positions.
        const seen = new Set<string>();
        for (let i = 0; i < sentence.length; i++) {
          const c = sentence[i];
          if (!levelKanjiSet.has(c)) continue;
          if (seen.has(c)) continue; // only index the first occurrence per char
          seen.add(c);
          const arr = out.get(c) ?? [];
          arr.push({ wordJp: w.jp, example: ex, blankIndex: i, sentence });
          out.set(c, arr);
        }
      }
    }
    return out;
  });

  const coverage = $derived(index.size);  // how many level-kanji actually have sentences

  function pickRandom(): Question | null {
    // Pick a random kanji from the index (coverage may be less than
    // levelKanjiSet if not every kanji appears in any example sentence).
    const keys = [...index.keys()];
    if (keys.length === 0) return null;
    const ch = keys[Math.floor(Math.random() * keys.length)];
    const triples = index.get(ch)!;
    const t = triples[Math.floor(Math.random() * triples.length)];
    const k = b.kanji[ch];
    if (!k) return null;
    return {
      kanji: k,
      example: t.example,
      blankIndex: t.blankIndex,
      sentence: t.sentence,
      wordJp: t.wordJp,
    };
  }

  // ── State ─────────────────────────────────────────────────────────────

  let current = $state<Question | null>(null);
  let drawScore = $state<number | null>(null);
  let solvedCount = $state(0);
  let attemptedCount = $state(0);
  let showingRef = $state(false);

  onMount(() => {
    current = pickRandom();
  });

  // Masked sentence: replace the blank kanji with ◻. We only blank the
  // first occurrence matching blankIndex — repeated occurrences of the same
  // kanji in one sentence stay visible (contextual hint).
  const maskedSentence = $derived.by(() => {
    if (!current) return '';
    const s = current.sentence;
    return s.slice(0, current.blankIndex) + '◻' + s.slice(current.blankIndex + 1);
  });

  // ── Score handling ────────────────────────────────────────────────────

  async function onScore(score: number) {
    if (!current || drawScore !== null) return;
    drawScore = score;
    attemptedCount++;
    const ch = current.kanji.char;

    // Persist per-kanji best score under the mode-aware key.
    const key = await fillKanjiScoreKey();
    const scores = (await getMeta<Record<string, number>>(key)) ?? {};
    const prev = scores[ch] ?? 0;
    const best = Math.max(prev, score);
    if (best !== prev) {
      scores[ch] = best;
      await putMeta(key, scores);
    }

    if (score >= 70) {
      solvedCount++;
    } else {
      // Record for Reinforce — same type as the regular writing drill so
      // practice converges.
      recordMistake({ type: 'kanji-writing', id: ch }).catch(() => {});
    }
  }

  function nextQuestion() {
    drawScore = null;
    showingRef = false;
    current = pickRandom();
  }
</script>

<div class="nav-links">
  <a class="back" href="/" use:link>← Home</a>
</div>

{#if !current}
  <div class="center muted">
    {#if coverage === 0}
      <h2>No eligible sentences</h2>
      <p>
        {filter === 'all'
          ? 'The bundle has no usable example sentences with kanji.'
          : `No level-${filter} kanji appear in any example sentence. Try a different level on Home.`}
      </p>
    {:else}
      <p>Loading…</p>
    {/if}
  </div>
{:else}
  <!-- ── Status strip ──────────────────────────────────────────────────── -->
  <div class="meta">
    Fill-in · {filter === 'all' ? 'All levels' : `Lvl ${filter}`} · {solvedCount}/{attemptedCount} correct
  </div>

  <!-- ── Masked sentence prompt ───────────────────────────────────────── -->
  <div class="prompt-card">
    <div class="masked-sentence">
      {#each maskedSentence as ch, i}{#if ch === '◻'}<span class="blank">？</span>{:else}<span>{ch}</span>{/if}{/each}
    </div>
    <div class="en-hint">{current.example.en}</div>
    <div class="speak-hint">
      <button
        class="speak-btn"
        onclick={() => speakJa(current!.sentence.replace(current!.kanji.char, ''))}
        aria-label="Hear sentence (skipping the blank)"
      >🔊 Hear sentence</button>
    </div>
  </div>

  <!-- ── Drawing UI ───────────────────────────────────────────────────── -->
  <div class="draw-header">
    <p class="quiz-hint">Write the missing kanji:</p>
    <div class="peek-col">
      {#key current.kanji.char + '-peek'}
        <RevealKanji svg={current.kanji.svg} strokeCount={Math.min(3, current.kanji.strokes)} />
      {/key}
      <span class="peek-hint">max 3 peeks</span>
    </div>
  </div>

  {#key current.kanji.char + '-morph'}
    <PracticeMorph
      kanji={current.kanji}
      minimal={true}
      hideRefOnMount={true}
      {onScore}
      onRefChange={(v) => (showingRef = v)}
    />
  {/key}

  <!-- ── Reveal after scoring ─────────────────────────────────────────── -->
  {#if drawScore !== null}
    <div class="answer-reveal">
      <div class="revealed-sentence">
        <Furigana segments={current.example.segs} />
      </div>
      <div class="reveal-meaning">
        Target kanji: <span class="hero-kanji">{current.kanji.char}</span>
        · <span class="reveal-reading">{current.kanji.kun.map((r) => r.replace(/[.\-]/g, ''))[0] ?? current.kanji.on[0] ?? ''}</span>
      </div>
      <div class="reveal-meaning">{current.kanji.meanings.slice(0, 3).join(', ')}</div>
      <div class="draw-score-line" class:ok={drawScore >= 70} class:bad={drawScore < 70}>
        Score: {drawScore} / 100 · {drawScore >= 70 ? 'passed ✓' : 'try again ✗'}
      </div>
    </div>
    <div class="actions single">
      <button class="primary" onclick={nextQuestion}>Next →</button>
    </div>
  {/if}
{/if}

<style>
  .nav-links { display: flex; gap: 0.25rem; flex-wrap: wrap; }
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); font-size: 0.9rem; }
  .center { padding: 2rem; text-align: center; }
  .muted { color: var(--fg-dim); }
  .meta { text-align: center; color: var(--fg-dim); font-size: 0.85rem; padding: 0.5rem; }

  .prompt-card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.25rem 1rem;
    margin: 0.5rem 1rem 0.75rem;
    text-align: center;
  }
  .masked-sentence {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 1.5rem;
    line-height: 2;
    letter-spacing: 0.02em;
  }
  .blank {
    display: inline-block;
    min-width: 1.5em;
    padding: 0 0.15em;
    border: 2px dashed var(--accent);
    border-radius: 6px;
    color: var(--accent);
    background: rgba(255, 122, 89, 0.08);
    margin: 0 0.1em;
    font-weight: 600;
  }
  .en-hint {
    margin-top: 0.6rem;
    color: var(--fg-dim);
    font-size: 0.92rem;
    line-height: 1.4;
  }
  .speak-hint { margin-top: 0.5rem; }
  .speak-btn {
    padding: 0.35rem 0.8rem;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 0.85rem;
    color: var(--fg-dim);
    cursor: pointer;
  }
  .speak-btn:hover { border-color: var(--accent); color: var(--fg); }

  .draw-header {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    padding: 0.5rem 1rem;
    max-width: 560px;
    margin: 0 auto;
  }
  .quiz-hint { color: var(--fg-dim); font-size: 0.9rem; margin: 0; }
  .peek-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    flex-shrink: 0;
  }
  .peek-hint { color: var(--fg-dim); font-size: 0.7rem; letter-spacing: 0.03em; }

  .answer-reveal {
    text-align: center;
    padding: 0.75rem 1rem 0;
  }
  .revealed-sentence {
    font-size: 1.3rem;
    line-height: 2.3;
    margin-bottom: 0.5rem;
  }
  .reveal-meaning {
    font-size: 0.95rem;
    color: var(--fg);
    margin-top: 0.25rem;
  }
  .hero-kanji {
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.3rem;
    color: var(--accent);
  }
  .reveal-reading {
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
    color: var(--accent);
  }
  .draw-score-line {
    font-size: 1rem;
    font-variant-numeric: tabular-nums;
    margin-top: 0.5rem;
  }
  .draw-score-line.ok { color: var(--ok); }
  .draw-score-line.bad { color: var(--err); }
  .actions { display: flex; gap: 0.5rem; padding: 1rem; justify-content: center; }
  .actions.single button { min-width: 12rem; padding: 0.8rem 1.5rem; border-radius: 10px; border: 1px solid var(--border); background: var(--accent); color: #1b1b1f; font-weight: 600; cursor: pointer; }
  .primary { padding: 0.6rem 1.2rem; border-radius: 10px; border: 1px solid var(--accent); background: var(--accent); color: #1b1b1f; font-weight: 600; cursor: pointer; }
</style>
