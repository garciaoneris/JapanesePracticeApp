<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { link } from 'svelte-spa-router';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import { bundle } from '../lib/data/bundle';
  import { fillKanjiScoreKey } from '../lib/data/mode';
  import { getMeta, putMeta } from '../lib/data/db';
  import { recordMistake } from '../lib/data/mistakes';
  import { speakJa } from '../lib/speech/tts';
  import { exampleJp } from '../lib/data/types';
  import type { Kanji, Example } from '../lib/data/types';
  import { startTick, stopTick } from '../lib/gamification/goal';
  import { addXp } from '../lib/gamification/xp';

  // ── Level handling (mirrors Home.svelte) ───────────────────────────────
  // Levels: 1=N5, 2=N4, 3=N3+N2, 4=N1, 5=ungraded jouyou/jinmeiyou.
  // For sentence-eligibility we allow any kanji at the current level OR
  // BELOW (so a Lvl 3 drill never surfaces a Lvl 4 N1 kanji the learner
  // hasn't encountered yet).
  const LEVEL_JLPT: Record<number, number[]> = {
    1: [5], 2: [4], 3: [3, 2], 4: [1], 5: [0],
  };
  /** JLPT values allowed in the sentence at a given level (level AND all lower). */
  const LEVEL_JLPT_CUMULATIVE: Record<number, number[]> = {
    1: [5],
    2: [5, 4],
    3: [5, 4, 3, 2],
    4: [5, 4, 3, 2, 1],
    5: [5, 4, 3, 2, 1, 0],
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
    /** Example containing this kanji. */
    example: Example;
    /** Index into example.segs of the segment we'll blank out. The segment
     *  is guaranteed to be a single-kanji seg matching `kanji.char` — this
     *  lets us render a clean blank box inline with the rest of the
     *  sentence's furigana instead of trying to mask mid-compound. */
    targetSegIndex: number;
    /** Pre-reconstructed sentence string (used only for spoken-audio
     *  playback after the answer). */
    sentence: string;
    /** Word whose example we picked from (for speaking, etc.). */
    wordJp: string;
  }

  const b = bundle();
  /** Kanji eligible to BE the blank target — only at the current level. */
  const targetLevelSet = $derived.by<Set<string>>(() => {
    if (filter === 'all') return new Set(Object.keys(b.kanji));
    const wanted = LEVEL_JLPT[filter] ?? [];
    return new Set(
      Object.values(b.kanji)
        .filter((k) => wanted.includes(k.jlpt))
        .map((k) => k.char),
    );
  });
  /** Kanji allowed to APPEAR anywhere in the sentence — target level AND
   *  everything below. Keeps surrounding characters at a level the learner
   *  has already encountered. */
  const allowedSentenceKanji = $derived.by<Set<string>>(() => {
    if (filter === 'all') return new Set(Object.keys(b.kanji));
    const wanted = LEVEL_JLPT_CUMULATIVE[filter] ?? [];
    return new Set(
      Object.values(b.kanji)
        .filter((k) => wanted.includes(k.jlpt))
        .map((k) => k.char),
    );
  });

  /** Pre-index: kanji char → list of (word, example, target-seg-index) triples.
   *  Only includes examples whose every kanji is allowed at or below level. */
  type Triple = { wordJp: string; example: Example; targetSegIndex: number; sentence: string };
  const index = $derived.by<Map<string, Triple[]>>(() => {
    const out = new Map<string, Triple[]>();
    const CJK_MIN = 0x4e00, CJK_MAX = 0x9fff;
    const isKanji = (c: string) => {
      const cp = c.codePointAt(0);
      return cp !== undefined && cp >= CJK_MIN && cp <= CJK_MAX;
    };
    for (const w of Object.values(b.words)) {
      if (!w.examples || w.examples.length === 0) continue;
      for (const ex of w.examples) {
        if (!ex.segs || ex.segs.length === 0) continue;
        const sentence = exampleJp(ex);
        if (!sentence) continue;
        // Reject the whole example if ANY kanji in it falls outside the
        // allowed-sentence set (i.e. above the user's level).
        let sentenceOk = true;
        for (const c of sentence) {
          if (isKanji(c) && !allowedSentenceKanji.has(c)) {
            sentenceOk = false;
            break;
          }
        }
        if (!sentenceOk) continue;
        // Look for single-kanji segs we can cleanly blank out. Only the
        // first occurrence per kanji in this sentence is indexed.
        const seen = new Set<string>();
        for (let i = 0; i < ex.segs.length; i++) {
          const t = ex.segs[i].t;
          if (t.length !== 1 || !isKanji(t)) continue;
          if (!targetLevelSet.has(t)) continue;
          if (seen.has(t)) continue;
          seen.add(t);
          const arr = out.get(t) ?? [];
          arr.push({ wordJp: w.jp, example: ex, targetSegIndex: i, sentence });
          out.set(t, arr);
        }
      }
    }
    return out;
  });

  const coverage = $derived(index.size);

  function pickRandom(): Question | null {
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
      targetSegIndex: t.targetSegIndex,
      sentence: t.sentence,
      wordJp: t.wordJp,
    };
  }

  /** True if any codepoint in `s` is in the CJK Unified Ideographs block. */
  function segHasKanji(s: string): boolean {
    for (const c of s) {
      const cp = c.codePointAt(0);
      if (cp !== undefined && cp >= 0x4e00 && cp <= 0x9fff) return true;
    }
    return false;
  }

  // ── State ─────────────────────────────────────────────────────────────

  let current = $state<Question | null>(null);
  let drawScore = $state<number | null>(null);
  let solvedCount = $state(0);
  let attemptedCount = $state(0);
  let showingRef = $state(false);

  onMount(() => {
    current = pickRandom();
    startTick();
  });
  onDestroy(() => stopTick());

  // Filled (non-blanked) version of the target segment, used in the reveal
  // state — same data as the original so Furigana keeps its reading / gloss.
  // No derived state needed: we just skip the blank class for that seg.

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
    // XP: +12 for a successful fill (same as Review draw-mode — this is a
    // harder task than meaning-choice), +2 effort credit otherwise.
    addXp(score >= 70 ? 12 : 2).catch(() => {});
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

  <!-- ── Sentence prompt ──────────────────────────────────────────────
       Renders inline: each non-target seg gets its furigana; the target
       seg becomes a dashed blank box while unanswered, and flips back to
       the real kanji with its reading once the user has scored.
       ─────────────────────────────────────────────────────────────── -->
  <div class="prompt-card">
    <div class="sentence-line">
      {#each current.example.segs as seg, i}
        {#if i === current.targetSegIndex && drawScore === null}
          <span class="blank" aria-label="missing kanji">？</span>
        {:else if segHasKanji(seg.t)}
          <ruby>{seg.t}<rt>{seg.r ?? ''}</rt></ruby>
        {:else}
          <span>{seg.t}</span>
        {/if}
      {/each}
    </div>
    <div class="en-hint">{current.example.en}</div>
    <!-- Always rendered so the card height is stable between unanswered
         and revealed states; visibility toggles so the button only acts
         once the blank is filled in. -->
    <div class="speak-hint" class:hidden={drawScore === null}>
      <button
        class="speak-btn"
        onclick={() => speakJa(current!.sentence)}
        aria-label="Hear the full sentence"
        disabled={drawScore === null}
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
      <div class="reveal-meaning">
        Answer: <span class="hero-kanji">{current.kanji.char}</span>
        · <span class="reveal-reading">{current.kanji.kun.map((r) => r.replace(/[.\-]/g, ''))[0] ?? current.kanji.on[0] ?? ''}</span>
        · {current.kanji.meanings.slice(0, 3).join(', ')}
      </div>
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
  .sentence-line {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 1.5rem;
    line-height: 2.4;
    letter-spacing: 0.02em;
  }
  .sentence-line ruby { ruby-position: over; }
  .sentence-line rt {
    font-size: 0.55em;
    color: var(--accent);
    font-weight: 500;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
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
  .speak-hint.hidden { visibility: hidden; }
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
