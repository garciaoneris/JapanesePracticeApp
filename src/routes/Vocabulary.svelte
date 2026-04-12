<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { loadKnownKanji } from '../lib/data/known';
  import { getAllBestScores, getMeta, putMeta } from '../lib/data/db';
  import { quizScoreKey } from '../lib/data/mode';
  import type { Kanji, Word } from '../lib/data/types';

  // ── Helpers ──────────────────────────────────────────────────────────
  function toHira(s: string): string {
    return [...s]
      .map((c) => {
        const cp = c.codePointAt(0)!;
        return cp >= 0x30a1 && cp <= 0x30f6 ? String.fromCodePoint(cp - 0x60) : c;
      })
      .join('');
  }

  function primaryReading(on: string[], kun: string[]): string {
    const clean = (s: string) => s.replace(/[.\-]/g, '').trim();
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

  function shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // ── State ────────────────────────────────────────────────────────────
  let mode = $state<'grid' | 'words' | 'quiz'>('grid');
  let selectedKanji = $state<string | null>(null);

  let knownKanji = $state<Set<string>>(new Set());
  let bestScores = $state<Map<string, number>>(new Map());
  /** Quiz scores per kanji: char → percentage (0–100). Stored in IndexedDB
   *  meta store as 'quiz-scores' — a separate scale from stroke-drawing. */
  let quizScores = $state<Map<string, number>>(new Map());

  let _qsKey = '';  // resolved quiz-score meta key for this mode

  onMount(async () => {
    _qsKey = await quizScoreKey();
    const [known, scores, qs] = await Promise.all([
      loadKnownKanji(),
      getAllBestScores(),
      getMeta<Record<string, number>>(_qsKey),
    ]);
    knownKanji = known;
    bestScores = scores;
    if (qs) quizScores = new Map(Object.entries(qs));

    // If navigating back from a word detail page, re-open the kanji's words view.
    const openKanji = sessionStorage.getItem('vocab-open-kanji');
    if (openKanji) {
      sessionStorage.removeItem('vocab-open-kanji');
      if (b.kanji[openKanji]) {
        selectedKanji = openKanji;
        mode = 'words';
      }
    }
  });

  const b = bundle();

  // ── Grid mode: mastered kanji (score >= 80) ──────────────────────────
  const masteredKanjiList = $derived.by<Kanji[]>(() => {
    if (bestScores.size === 0) return [];
    const out: Kanji[] = [];
    for (const k of Object.values(b.kanji)) {
      const s = bestScores.get(k.char);
      if (s !== undefined && s >= 80) out.push(k);
    }
    out.sort((a, c) => {
      if (c.jlpt !== a.jlpt) return c.jlpt - a.jlpt;
      const ag = a.grade || 99;
      const cg = c.grade || 99;
      if (ag !== cg) return ag - cg;
      return a.strokes - c.strokes;
    });
    return out;
  });

  // ── Words mode: words for the selected kanji ─────────────────────────
  const selectedKanjiData = $derived(selectedKanji ? b.kanji[selectedKanji] ?? null : null);

  const readyWords = $derived.by<Word[]>(() => {
    if (!selectedKanji || knownKanji.size === 0) return [];
    const out: Word[] = [];
    for (const w of Object.values(b.words)) {
      if (w.kanji.length === 0) continue;
      if (!w.kanji.includes(selectedKanji)) continue;
      if (w.kanji.every((c) => knownKanji.has(c))) out.push(w);
    }
    out.sort(
      (a, c) =>
        a.kanji.length - c.kanji.length ||
        [...a.jp].length - [...c.jp].length ||
        a.reading.length - c.reading.length,
    );
    return out;
  });

  // ── All mastered words (for distractor padding) ──────────────────────
  const allMasteredWords = $derived.by<Word[]>(() => {
    if (knownKanji.size === 0) return [];
    const out: Word[] = [];
    for (const w of Object.values(b.words)) {
      if (w.kanji.length === 0) continue;
      if (w.kanji.every((c) => knownKanji.has(c))) out.push(w);
    }
    return out;
  });

  // ── Quiz state ───────────────────────────────────────────────────────
  interface QuizQuestion {
    word: Word;
    type: 'reading' | 'meaning';
    choices: string[];
    correctIdx: number;
  }

  let quizQuestions = $state<QuizQuestion[]>([]);
  let quizIdx = $state(0);
  let quizPicked = $state<number | null>(null);
  let quizCorrectCount = $state(0);
  let quizFinished = $state(false);

  /** Could this meaning be confused with a romanized Japanese reading?
   *  Single lowercase words like "mawashi", "tofu" look like romaji. */
  function looksLikeRomaji(s: string): boolean {
    return /^[a-z]+$/i.test(s) && s.length < 10;
  }

  function buildDistractors(correct: string, pool: string[], count: number, filterRomaji = false): string[] {
    let candidates = pool.filter((x) => x !== correct && x.length > 0);
    if (filterRomaji) candidates = candidates.filter((x) => !looksLikeRomaji(x));
    const unique = [...new Set(candidates)];
    return shuffle(unique).slice(0, count);
  }

  function startQuiz(): void {
    const words = shuffle(readyWords).slice(0, 8);
    const questions: QuizQuestion[] = [];

    // Gather distractor pools from ready words + all mastered words as fallback.
    const readingPool = readyWords.map((w) => w.reading);
    const meaningPool = readyWords.map((w) => w.meanings[0] ?? '');
    const allReadingPool = allMasteredWords.map((w) => w.reading);
    const allMeaningPool = allMasteredWords.map((w) => w.meanings[0] ?? '');

    for (const w of words) {
      // Reading question
      let rDistractors = buildDistractors(w.reading, readingPool, 3);
      if (rDistractors.length < 3) {
        const extra = buildDistractors(w.reading, allReadingPool, 3 - rDistractors.length);
        rDistractors = [...rDistractors, ...extra].slice(0, 3);
      }
      const rChoices = shuffle([w.reading, ...rDistractors]);
      questions.push({
        word: w,
        type: 'reading',
        choices: rChoices,
        correctIdx: rChoices.indexOf(w.reading),
      });

      // Meaning question — filter romaji-looking distractors
      const correctMeaning = w.meanings[0] ?? '';
      let mDistractors = buildDistractors(correctMeaning, meaningPool, 3, true);
      if (mDistractors.length < 3) {
        const extra = buildDistractors(correctMeaning, allMeaningPool, 3 - mDistractors.length, true);
        mDistractors = [...mDistractors, ...extra].slice(0, 3);
      }
      const mChoices = shuffle([correctMeaning, ...mDistractors]);
      questions.push({
        word: w,
        type: 'meaning',
        choices: mChoices,
        correctIdx: mChoices.indexOf(correctMeaning),
      });
    }

    quizQuestions = questions;
    quizIdx = 0;
    quizPicked = null;
    quizCorrectCount = 0;
    quizFinished = false;
    mode = 'quiz';
  }

  function pickAnswer(idx: number): void {
    if (quizPicked !== null) return;
    quizPicked = idx;
    if (idx === currentQuestion.correctIdx) quizCorrectCount++;
  }

  function nextQuestion(): void {
    if (quizIdx + 1 >= quizQuestions.length) {
      quizFinished = true;
      // Save quiz score for this kanji (keep best).
      if (selectedKanji) {
        const pct = Math.round((quizCorrectCount / quizQuestions.length) * 100);
        const prev = quizScores.get(selectedKanji) ?? 0;
        const best = Math.max(prev, pct);
        quizScores.set(selectedKanji, best);
        quizScores = new Map(quizScores); // trigger reactivity
        // Persist all quiz scores to IndexedDB.
        putMeta(_qsKey || 'quiz-scores', Object.fromEntries(quizScores)).catch(() => {});
      }
    } else {
      quizIdx++;
      quizPicked = null;
    }
  }

  const currentQuestion = $derived(quizQuestions[quizIdx]);

  // ── Cell styling — based on QUIZ scores, not stroke scores ───────────
  function quizCellColor(pct: number): string {
    if (pct === 100) return '#ffd24a'; // gold = perfect
    if (pct >= 50) {
      const t = (pct - 50) / 50;
      const r = Math.round(255 * (1 - t) + 94 * t);
      const g = Math.round(180 * (1 - t) + 202 * t);
      const b = Math.round(50 * (1 - t) + 124 * t);
      return `rgb(${r},${g},${b})`;
    }
    if (pct > 0) return '#ff6b6b';
    return '';
  }

  function cellStyle(char: string): string {
    const s = quizScores.get(char);
    if (s === undefined || s === 0) return '';
    const c = quizCellColor(s);
    return `border-color: ${c}; background: ${c}20;`;
  }

  function badgeStyle(char: string): string {
    const s = quizScores.get(char);
    if (s === undefined) return 'color: var(--fg-dim); border-color: var(--border);';
    const c = quizCellColor(s);
    return c ? `color: ${c}; border-color: ${c};` : '';
  }

  function badgeText(char: string): string {
    const s = quizScores.get(char);
    if (s === undefined) return '—';
    return `${s}%`;
  }

  // ── Navigation helpers ───────────────────────────────────────────────
  function selectKanji(char: string): void {
    selectedKanji = char;
    mode = 'words';
  }

  function backToGrid(): void {
    selectedKanji = null;
    mode = 'grid';
  }

  function backToWords(): void {
    mode = 'words';
  }

  // Quiz summary color — separate scale from kanji-writing scores:
  // gold (#ffd24a) for perfect, amber→green gradient for 50%–near-perfect,
  // red for below 50%.
  function quizScoreColor(correct: number, total: number): string {
    if (total === 0) return 'var(--fg-dim)';
    if (correct === total) return '#ffd24a'; // gold = perfect
    const pct = correct / total;
    if (pct >= 0.5) {
      // Lerp from green (1.0 = near-perfect) to amber (0.5)
      const t = (pct - 0.5) / 0.5; // 0 at 50%, 1 at 100%
      const r = Math.round(255 * (1 - t) + 94 * t);
      const g = Math.round(180 * (1 - t) + 202 * t);
      const b = Math.round(50 * (1 - t) + 124 * t);
      return `rgb(${r},${g},${b})`;
    }
    return 'var(--err)'; // below 50%
  }
</script>

<a class="back" href="/" use:link>← Home</a>

{#if mode === 'grid'}
  <!-- ── GRID MODE ──────────────────────────────────────────────────── -->
  <header class="head">
    <h1>Vocabulary</h1>
    <p class="subtitle">
      {#if masteredKanjiList.length > 0}
        <b>{masteredKanjiList.length}</b> mastered kanji — tap one to see words
      {:else}
        Your mastered kanji will appear here
      {/if}
    </p>
  </header>

  {#if masteredKanjiList.length === 0}
    <div class="empty">
      <p>Practice some kanji first!</p>
      <p class="empty-hint">Master kanji (score >= 80) and they'll unlock here with their vocabulary.</p>
      <a class="cta" href="/" use:link>Go practice</a>
    </div>
  {:else}
    <section class="kanji-section">
      <div class="grid">
        {#each masteredKanjiList as k (k.char)}
          <button
            class="cell"
            class:gold={(quizScores.get(k.char) ?? 0) === 100}
            style={cellStyle(k.char)}
            onclick={() => selectKanji(k.char)}
            aria-label={`${k.char} — ${k.meanings.join(', ')}`}
          >
            <span class="ch">{k.char}</span>
            <span class="lvl">{primaryReading(k.on, k.kun)}</span>
            <span class="score-badge" style={badgeStyle(k.char)}>{badgeText(k.char)}</span>
          </button>
        {/each}
      </div>
    </section>
  {/if}

{:else if mode === 'words'}
  <!-- ── WORDS MODE ─────────────────────────────────────────────────── -->
  <button class="back-btn" onclick={backToGrid}>← Back to vocabulary</button>

  {#if selectedKanjiData}
    <header class="words-header">
      <div class="words-kanji-big">{selectedKanjiData.char}</div>
      <div class="words-readings">
        {#if selectedKanjiData.on.length > 0}
          <span class="reading-label">On:</span>
          <span class="reading-values">{selectedKanjiData.on.map((r) => toHira(r.replace(/[.\-]/g, ''))).join(', ')}</span>
        {/if}
        {#if selectedKanjiData.kun.length > 0}
          <span class="reading-label">Kun:</span>
          <span class="reading-values">{selectedKanjiData.kun.map((r) => r.replace(/[.\-]/g, '')).join(', ')}</span>
        {/if}
      </div>
      <div class="words-meanings">{selectedKanjiData.meanings.join(', ')}</div>
    </header>

    <section class="words-section">
      <div class="words-toolbar">
        <h2>{readyWords.length} word{readyWords.length !== 1 ? 's' : ''} you can read</h2>
        <button
          class="quiz-btn"
          disabled={readyWords.length < 2}
          onclick={startQuiz}
          title={readyWords.length < 2 ? 'Need at least 2 words for a quiz' : 'Start quiz'}
        >
          Start quiz
        </button>
      </div>

      {#if readyWords.length === 0}
        <p class="no-words">No fully unlocked words yet for this kanji.</p>
      {:else}
        <div class="word-grid">
          {#each readyWords as w (w.id)}
            <a class="word-card" href={`/vocab/${encodeURIComponent(w.id)}`} use:link>
              <div class="wc-jp">{w.jp}</div>
              <div class="wc-reading">{w.reading}</div>
              <div class="wc-en">{w.meanings[0] ?? ''}</div>
            </a>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

{:else if mode === 'quiz'}
  <!-- ── QUIZ MODE ──────────────────────────────────────────────────── -->
  {#if quizFinished}
    <div class="quiz-summary">
      <h1>Quiz Complete</h1>
      <div
        class="summary-score"
        style="color: {quizScoreColor(quizCorrectCount, quizQuestions.length)}"
      >
        {quizCorrectCount} / {quizQuestions.length}
      </div>
      <p class="summary-label">correct answers</p>
      <button class="cta" onclick={backToWords}>Back to words</button>
    </div>
  {:else if currentQuestion}
    <div class="quiz-container">
      <div class="quiz-progress">
        Question {quizIdx + 1} of {quizQuestions.length}
      </div>

      <div class="quiz-prompt">
        {#if currentQuestion.type === 'reading'}
          <p class="quiz-instruction">What is the reading?</p>
          <div class="quiz-word">{currentQuestion.word.jp}</div>
        {:else}
          <p class="quiz-instruction">What does this mean?</p>
          <div class="quiz-word">{currentQuestion.word.jp}</div>
          <div class="quiz-word-reading">{currentQuestion.word.reading}</div>
        {/if}
      </div>

      <div class="quiz-choices">
        {#each currentQuestion.choices as choice, i}
          <button
            class="choice-btn"
            class:correct={quizPicked !== null && i === currentQuestion.correctIdx}
            class:wrong={quizPicked !== null && i === quizPicked && i !== currentQuestion.correctIdx}
            class:dimmed={quizPicked !== null && i !== currentQuestion.correctIdx && i !== quizPicked}
            disabled={quizPicked !== null}
            onclick={() => pickAnswer(i)}
          >
            {choice}
          </button>
        {/each}
      </div>

      {#if quizPicked !== null}
        <button class="next-btn" onclick={nextQuestion}>
          {quizIdx + 1 >= quizQuestions.length ? 'See results' : 'Next'}
        </button>
      {/if}
    </div>
  {/if}
{/if}

<style>
  /* ── Shared ─────────────────────────────────────────────────────────── */
  .back {
    display: inline-block;
    padding: 0.75rem 1rem;
    color: var(--fg-dim);
    font-size: 0.9rem;
  }
  .back-btn {
    display: inline-block;
    padding: 0.75rem 1rem;
    color: var(--fg-dim);
    font-size: 0.9rem;
    background: none;
    border: none;
    cursor: pointer;
    font-family: inherit;
  }
  .back-btn:hover {
    color: var(--fg);
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
  .empty p {
    margin: 0 0 0.5rem;
  }
  .empty-hint {
    font-size: 0.85rem;
    opacity: 0.7;
  }
  .cta {
    display: inline-block;
    margin-top: 1rem;
    padding: 0.75rem 1.4rem;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    color: #1b1b1f;
    font-weight: 600;
    font-size: 0.95rem;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: transform 0.1s;
  }
  .cta:active {
    transform: scale(0.97);
  }

  /* ── Grid mode ──────────────────────────────────────────────────────── */
  .kanji-section {
    padding: 0.5rem 1rem 2.5rem;
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
    cursor: pointer;
    padding: 0;
  }
  .cell:hover {
    background: var(--bg-elevated);
  }
  .cell:active {
    transform: scale(0.94);
  }
  .cell.gold {
    box-shadow: 0 0 0 2px rgba(255, 210, 74, 0.4), 0 8px 22px rgba(255, 210, 74, 0.2);
  }
  .ch {
    font-size: 1.9rem;
    line-height: 1;
  }
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

  /* ── Words mode ─────────────────────────────────────────────────────── */
  .words-header {
    text-align: center;
    padding: 0.5rem 1rem 1.2rem;
  }
  .words-kanji-big {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 4rem;
    line-height: 1.1;
  }
  .words-readings {
    margin-top: 0.5rem;
    font-size: 0.9rem;
    color: var(--fg-dim);
    display: flex;
    justify-content: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .reading-label {
    font-weight: 600;
    color: var(--fg);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .reading-values {
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
  }
  .words-meanings {
    margin-top: 0.4rem;
    font-size: 0.95rem;
    color: var(--fg);
  }
  .words-section {
    padding: 0 1rem 2.5rem;
  }
  .words-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.85rem;
    padding: 0 0.25rem;
  }
  .words-toolbar h2 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--fg-dim);
    margin: 0;
    font-weight: 600;
  }
  .quiz-btn {
    padding: 0.5rem 1.1rem;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    color: #1b1b1f;
    font-weight: 600;
    font-size: 0.85rem;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: transform 0.1s, opacity 0.15s;
  }
  .quiz-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .quiz-btn:not(:disabled):active {
    transform: scale(0.96);
  }
  .no-words {
    text-align: center;
    color: var(--fg-dim);
    padding: 2rem 0;
  }
  .word-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 0.6rem;
  }
  .word-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.85rem 0.9rem;
    background: var(--bg-alt);
    border: 1px solid rgba(94, 202, 124, 0.25);
    border-radius: 12px;
    color: var(--fg);
    transition: border-color 0.15s, transform 0.1s, background 0.15s;
  }
  .word-card:hover {
    border-color: rgba(255, 122, 89, 0.45);
    background: var(--bg-elevated);
  }
  .word-card:active {
    transform: scale(0.97);
  }
  .wc-jp {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 1.4rem;
    line-height: 1.1;
  }
  .wc-reading {
    color: var(--fg-dim);
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }
  .wc-en {
    color: var(--fg);
    font-size: 0.82rem;
    margin-top: 0.25rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ── Quiz mode ──────────────────────────────────────────────────────── */
  .quiz-container {
    max-width: 480px;
    margin: 0 auto;
    padding: 1.5rem 1rem 2.5rem;
  }
  .quiz-progress {
    text-align: center;
    font-size: 0.82rem;
    color: var(--fg-dim);
    margin-bottom: 1.5rem;
    font-variant-numeric: tabular-nums;
  }
  .quiz-prompt {
    text-align: center;
    margin-bottom: 2rem;
  }
  .quiz-instruction {
    font-size: 0.9rem;
    color: var(--fg-dim);
    margin: 0 0 0.8rem;
  }
  .quiz-word {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: 3rem;
    line-height: 1.15;
  }
  .quiz-word-reading {
    font-size: 1rem;
    color: var(--fg-dim);
    margin-top: 0.3rem;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
  }
  .quiz-choices {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .choice-btn {
    width: 100%;
    padding: 0.9rem 1rem;
    border-radius: 12px;
    background: var(--bg-alt);
    border: 2px solid var(--border);
    color: var(--fg);
    font-size: 1rem;
    font-family: inherit;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s, background 0.15s, transform 0.1s, opacity 0.15s;
  }
  .choice-btn:not(:disabled):hover {
    border-color: rgba(255, 122, 89, 0.45);
    background: var(--bg-elevated);
  }
  .choice-btn:not(:disabled):active {
    transform: scale(0.98);
  }
  .choice-btn.correct {
    background: rgba(94, 202, 124, 0.2);
    border-color: var(--ok);
  }
  .choice-btn.wrong {
    background: rgba(255, 107, 107, 0.2);
    border-color: var(--err);
  }
  .choice-btn.dimmed {
    opacity: 0.45;
  }
  .next-btn {
    display: block;
    width: 100%;
    margin-top: 1.2rem;
    padding: 0.85rem 1rem;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), #ff5a30);
    color: #1b1b1f;
    font-weight: 600;
    font-size: 0.95rem;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition: transform 0.1s;
  }
  .next-btn:active {
    transform: scale(0.97);
  }

  /* ── Quiz summary ───────────────────────────────────────────────────── */
  .quiz-summary {
    text-align: center;
    padding: 3rem 1.5rem;
  }
  .quiz-summary h1 {
    font-size: 1.6rem;
    margin: 0 0 1.5rem;
    letter-spacing: -0.01em;
  }
  .summary-score {
    font-size: 4rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .summary-label {
    margin: 0.5rem 0 0;
    color: var(--fg-dim);
    font-size: 0.95rem;
  }
</style>
