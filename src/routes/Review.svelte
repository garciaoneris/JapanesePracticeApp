<script lang="ts">
  import { link } from 'svelte-spa-router';
  import { onMount } from 'svelte';
  import { bundle } from '../lib/data/bundle';
  import { dueSrs, putSrs, getSrs, getAllBestScores, getMeta, putMeta } from '../lib/data/db';
  import { grade, newCard } from '../lib/srs/sm2';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { KNOWN_THRESHOLD } from '../lib/data/known';
  import type { Grade, SrsState } from '../lib/data/types';

  const NEW_PER_SESSION = 10;

  let queue = $state<SrsState[]>([]);
  let idx = $state(0);
  let showBack = $state(false);
  let done = $state(false);
  let reviewResults = $state<Map<string, {correct: number, total: number}>>(new Map());

  /** Read the JLPT filter from Home's sessionStorage. 'all' or a number 0-5. */
  function getJlptFilter(): number | null {
    const v = sessionStorage.getItem('home-jlpt-filter');
    if (!v || v === 'all') return null;
    const n = Number(v);
    return [0, 1, 2, 3, 4, 5].includes(n) ? n : null;
  }

  let jlptFilter = $state<number | null>(null);
  let jlptLabel = $derived(jlptFilter !== null && jlptFilter > 0 ? `N${jlptFilter}` : jlptFilter === 0 ? 'Ungraded' : '');

  /** Does this SRS card belong to the active JLPT filter? */
  function cardMatchesFilter(card: SrsState, b: ReturnType<typeof bundle>, jlpt: number): boolean {
    if (card.kind === 'kanji') {
      const ch = card.id.replace('kanji:', '');
      const k = b.kanji[ch];
      return k ? k.jlpt === jlpt : false;
    }
    // Word card: matches if ANY of its kanji is at the filtered level.
    const wid = card.id.replace('word:', '');
    const w = b.words[wid];
    if (!w) return false;
    return w.kanji.some((ch) => b.kanji[ch]?.jlpt === jlpt);
  }

  async function buildQueue() {
    const now = Date.now();
    const b = bundle();
    jlptFilter = getJlptFilter();

    let due = await dueSrs(now, 200);

    // Filter due cards by JLPT level if a filter is active.
    if (jlptFilter !== null) {
      due = due.filter((c) => cardMatchesFilter(c, b, jlptFilter!));
    }

    // Top up with new cards for kanji/words the user has already mastered
    // (score >= 80) but hasn't been quizzed on via SRS yet.
    if (due.length < NEW_PER_SESSION) {
      const native = await getMeta<boolean>('native-mode');
      const scores = await getAllBestScores();
      const need = NEW_PER_SESSION - due.length;
      const newCandidates: SrsState[] = [];
      for (const k of Object.values(b.kanji)) {
        if (newCandidates.length >= need) break;
        if (!native && (scores.get(k.char) ?? 0) < KNOWN_THRESHOLD) continue;
        if (jlptFilter !== null && k.jlpt !== jlptFilter) continue;
        const id = `kanji:${k.char}`;
        if (!(await getSrs(id))) newCandidates.push(newCard(id, 'kanji', now));
      }
      for (const w of Object.values(b.words)) {
        if (newCandidates.length >= need) break;
        if (!native && w.kanji.length > 0 && !w.kanji.every((c) => (scores.get(c) ?? 0) >= KNOWN_THRESHOLD)) continue;
        if (jlptFilter !== null && !w.kanji.some((ch) => b.kanji[ch]?.jlpt === jlptFilter)) continue;
        const id = `word:${w.id}`;
        if (!(await getSrs(id))) newCandidates.push(newCard(id, 'word', now));
      }
      for (const c of newCandidates) await putSrs(c);
      due.push(...newCandidates);
    }

    // Shuffle.
    for (let i = due.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [due[i], due[j]] = [due[j], due[i]];
    }
    queue = due;
    idx = 0;
    showBack = false;
    done = queue.length === 0;
  }

  onMount(buildQueue);

  const current = $derived(queue[idx]);
  const display = $derived.by(() => {
    if (!current) return null;
    const b = bundle();
    if (current.kind === 'kanji') {
      const key = current.id.slice('kanji:'.length);
      return { kind: 'kanji' as const, kanji: b.kanji[key] };
    } else {
      const key = current.id.slice('word:'.length);
      return { kind: 'word' as const, word: b.words[key] };
    }
  });

  // ── Multiple-choice quiz ──────────────────────────────────────────────
  let choices = $state<string[]>([]);
  let correctChoice = $state('');
  let picked = $state<number | null>(null);

  function shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  /** Build 4 meaning choices for the current card. */
  function buildChoices() {
    if (!display) return;
    const b = bundle();
    let correct: string;
    if (display.kind === 'kanji' && display.kanji) {
      correct = display.kanji.meanings.slice(0, 2).join(', ');
    } else if (display.kind === 'word' && display.word) {
      correct = display.word.meanings[0] ?? '';
    } else {
      return;
    }
    correctChoice = correct;

    // Gather distractors from other kanji/words in the same JLPT level.
    const pool: string[] = [];
    for (const k of Object.values(b.kanji)) {
      const m = k.meanings.slice(0, 2).join(', ');
      if (m && m !== correct) pool.push(m);
    }
    const distractors = shuffle(pool).slice(0, 3);
    choices = shuffle([correct, ...distractors]);
    picked = null;
  }

  // Build choices whenever the card changes.
  $effect(() => {
    if (display) buildChoices();
  });

  async function pickChoice(i: number) {
    if (picked !== null) return;
    picked = i;
    const isCorrect = choices[i] === correctChoice;
    // Auto-grade: correct = 'good', wrong = 'again'
    if (!current) return;
    const g: Grade = isCorrect ? 'good' : 'again';
    const next = grade(current, g);
    await putSrs(next);

    // Track per-kanji review result
    const ch = current.kind === 'kanji'
      ? current.id.replace('kanji:', '')
      : current.id.replace('word:', '').charAt(0);
    const prev = reviewResults.get(ch) ?? { correct: 0, total: 0 };
    reviewResults.set(ch, { correct: prev.correct + (isCorrect ? 1 : 0), total: prev.total + 1 });
  }

  async function advance() {
    if (idx + 1 >= queue.length) {
      done = true;
      // Save per-kanji review percentages (keep best)
      const existing = (await getMeta<Record<string, number>>('review-scores')) ?? {};
      for (const [ch, r] of reviewResults) {
        const pct = Math.round((r.correct / r.total) * 100);
        existing[ch] = Math.max(existing[ch] ?? 0, pct);
      }
      await putMeta('review-scores', existing);
    } else {
      idx += 1;
      showBack = false;
      picked = null;
    }
  }
</script>

<a class="back" href="/" use:link>← Back</a>
{#if jlptLabel}
  <div class="filter-tag">Reviewing: {jlptLabel} only</div>
{/if}

{#if done}
  <div class="center">
    <h2>All done for now!</h2>
    <p class="muted">Reviewed {queue.length} card{queue.length === 1 ? '' : 's'}.</p>
    <button class="primary" onclick={buildQueue}>Another round</button>
  </div>
{:else if !current || !display}
  <div class="center muted">Loading…</div>
{:else}
  <div class="meta">Card {idx + 1} / {queue.length}</div>
  <div class="card">
    {#if display.kind === 'kanji' && display.kanji}
      <div class="kanji-big">{display.kanji.char}</div>
      <p class="quiz-hint">What does this mean?</p>
    {:else if display.kind === 'word' && display.word}
      <div class="word-front">{display.word.jp}</div>
      <div class="word-reading-hint">{display.word.reading}</div>
      <p class="quiz-hint">What does this mean?</p>
    {/if}
  </div>

  <div class="choices">
    {#each choices as choice, i}
      <button
        class="choice-btn"
        class:correct={picked !== null && choice === correctChoice}
        class:wrong={picked !== null && i === picked && choice !== correctChoice}
        class:dimmed={picked !== null && choice !== correctChoice && i !== picked}
        disabled={picked !== null}
        onclick={() => pickChoice(i)}
      >
        {choice}
      </button>
    {/each}
  </div>

  {#if picked !== null}
    <div class="actions single">
      <button class="primary" onclick={advance}>
        {idx + 1 >= queue.length ? 'Finish' : 'Next →'}
      </button>
    </div>
  {/if}

  {#if display.kind === 'kanji' && display.kanji}
    <div class="jump">
      <a href={`/learn/${encodeURIComponent(display.kanji.char)}`} use:link>Open lesson →</a>
    </div>
  {:else if display.kind === 'word' && display.word}
    <div class="jump">
      <a href={`/vocab/${encodeURIComponent(display.word.id)}`} use:link>Open card →</a>
    </div>
  {/if}
{/if}

<style>
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); }
  .filter-tag {
    text-align: center;
    font-size: 0.85rem;
    color: var(--accent);
    padding: 0.25rem 0;
    letter-spacing: 0.03em;
  }
  .center { padding: 2rem; text-align: center; }
  .meta { text-align: center; color: var(--fg-dim); font-size: 0.85rem; padding: 0.5rem; }
  .card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2rem 1.5rem;
    margin: 0.5rem 1rem;
    text-align: center;
    min-height: 14rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
  }
  .word-front { font-size: 3rem; font-family: 'Hiragino Mincho ProN', serif; }
  .back-body { display: flex; flex-direction: column; gap: 0.5rem; align-items: center; }
  .readings { display: flex; gap: 1.5rem; color: var(--fg-dim); }
  .lbl { color: var(--fg-dim); font-size: 0.75rem; text-transform: uppercase; margin-right: 0.4em; }
  .reading { color: var(--fg-dim); font-size: 1.3rem; }
  .en { font-size: 1.1rem; }
  .quiz-hint { color: var(--fg-dim); font-size: 0.9rem; margin: 0; }
  .word-reading-hint { color: var(--accent); font-size: 1.2rem; }
  .choices {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    max-width: 500px;
    margin: 0 auto;
  }
  .choice-btn {
    width: 100%;
    padding: 0.9rem 1rem;
    border-radius: 12px;
    background: var(--bg-alt);
    border: 1.5px solid var(--border);
    color: var(--fg);
    font-size: 0.95rem;
    text-align: left;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s;
  }
  .choice-btn:hover:not(:disabled) {
    background: var(--bg-elevated);
    border-color: var(--fg-dim);
  }
  .choice-btn.correct {
    background: rgba(94, 202, 124, 0.2);
    border-color: var(--ok);
    color: var(--ok);
  }
  .choice-btn.wrong {
    background: rgba(255, 107, 107, 0.2);
    border-color: var(--err);
    color: var(--err);
  }
  .choice-btn.dimmed {
    opacity: 0.4;
  }
  .actions { display: flex; gap: 0.5rem; padding: 1rem; justify-content: center; }
  .actions.single button { min-width: 12rem; }
  .jump { text-align: center; padding: 0.5rem 1rem 2rem; }
  .muted { color: var(--fg-dim); }
</style>
