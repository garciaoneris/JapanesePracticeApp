<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { speakJa } from '../lib/speech/tts';
  import { getMistakes, reinforceCorrect, reinforceWrong, type Mistake } from '../lib/data/mistakes';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import type { Kanji } from '../lib/data/types';
  import { startTick, stopTick } from '../lib/gamification/goal';
  import { addXp } from '../lib/gamification/xp';

  /** Choice-based question (word-reading, word-meaning, kanji-meaning). */
  type ChoiceQuestion = {
    mistake: Mistake;
    kind: 'choice';
    prompt: string;
    subPrompt?: string;
    instruction: string;
    choices: string[];
    correct: string;
    corrects: string[];
    speakText: string;
  };

  /** Draw-from-memory question (kanji-writing). */
  type DrawQuestion = {
    mistake: Mistake;
    kind: 'draw';
    kanji: Kanji;
    speakText: string;
  };

  type Question = ChoiceQuestion | DrawQuestion;

  let mistakes = $state<Mistake[]>([]);
  let questions = $state<Question[]>([]);
  let idx = $state(0);
  let picked = $state<number | null>(null);
  let drawScoreDone = $state<number | null>(null);
  let done = $state(false);
  let cleared = $state(0);
  let reinforcedCount = $state(0);

  const b = bundle();

  function shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  /** Build a Question from a Mistake. Returns null if data missing. */
  function buildQuestion(m: Mistake): Question | null {
    if (m.type === 'kanji-writing') {
      const k = b.kanji[m.id];
      if (!k) return null;
      return {
        mistake: m,
        kind: 'draw',
        kanji: k,
        speakText: k.kun[0] ?? k.on[0] ?? k.char,
      };
    }
    if (m.type === 'kanji-meaning') {
      const k = b.kanji[m.id];
      if (!k) return null;
      const correct = k.meanings.slice(0, 2).join(', ');
      const pool: string[] = [];
      for (const other of Object.values(b.kanji)) {
        const meaning = other.meanings.slice(0, 2).join(', ');
        if (meaning && meaning !== correct) pool.push(meaning);
      }
      const distractors = shuffle(pool).slice(0, 3);
      const choices = shuffle([correct, ...distractors]);
      return {
        mistake: m,
        kind: 'choice',
        prompt: k.char,
        instruction: 'What does this mean?',
        choices,
        correct,
        corrects: [correct],
        speakText: k.kun[0] ?? k.on[0] ?? k.char,
      };
    }
    // word-reading or word-meaning
    const w = b.words[m.id];
    if (!w) return null;
    if (m.type === 'word-reading') {
      const allCorrect = [w.reading, ...(w.altReadings ?? [])];
      const pool: string[] = [];
      for (const other of Object.values(b.words)) {
        if (other.reading && !allCorrect.includes(other.reading)) pool.push(other.reading);
      }
      const distractors = shuffle(pool).slice(0, 3);
      const choices = shuffle([...allCorrect, ...distractors].filter((v, i, a) => a.indexOf(v) === i).slice(0, 4));
      return {
        mistake: m,
        kind: 'choice',
        prompt: w.jp,
        instruction: 'What is the reading?',
        choices,
        correct: w.reading,
        corrects: allCorrect,
        speakText: w.jp,
      };
    }
    // word-meaning
    const correct = w.meanings[0] ?? '';
    if (!correct) return null;
    const pool: string[] = [];
    for (const other of Object.values(b.words)) {
      const meaning = other.meanings[0] ?? '';
      if (meaning && meaning !== correct) pool.push(meaning);
    }
    const distractors = shuffle(pool).slice(0, 3);
    const choices = shuffle([correct, ...distractors]);
    return {
      mistake: m,
      kind: 'choice',
      prompt: w.jp,
      subPrompt: w.reading,
      instruction: 'What does this mean?',
      choices,
      correct,
      corrects: [correct],
      speakText: w.jp,
    };
  }

  async function buildQuestions() {
    mistakes = await getMistakes();
    const qs: Question[] = [];
    for (const m of shuffle(mistakes)) {
      const q = buildQuestion(m);
      if (q) qs.push(q);
    }
    questions = qs;
    idx = 0;
    picked = null;
    drawScoreDone = null;
    done = questions.length === 0;
    cleared = 0;
    reinforcedCount = 0;
  }

  onMount(() => { buildQuestions(); startTick(); });
  onDestroy(() => stopTick());

  const current = $derived(questions[idx]);

  async function recordOutcome(isCorrect: boolean) {
    if (!current) return;
    if (isCorrect) {
      const before = current.mistake.streak;
      await reinforceCorrect(current.mistake.type, current.mistake.id);
      if (before + 1 >= 3) cleared++;
      reinforcedCount++;
    } else {
      await reinforceWrong(current.mistake.type, current.mistake.id);
    }
    // XP: Reinforce is effortful comeback practice — +10 correct / +3 wrong,
    // a notch above plain Review so the learner sees returning to a mistake
    // as genuinely valuable.
    addXp(isCorrect ? 10 : 3).catch(() => {});
    speakJa(current.speakText);
  }

  async function pickChoice(i: number) {
    if (picked !== null || !current || current.kind !== 'choice') return;
    picked = i;
    const isCorrect = current.corrects.includes(current.choices[i]);
    await recordOutcome(isCorrect);
  }

  async function onDrawScore(score: number) {
    if (!current || current.kind !== 'draw' || drawScoreDone !== null) return;
    drawScoreDone = score;
    await recordOutcome(score >= 70);
  }

  function advance() {
    if (idx + 1 >= questions.length) {
      done = true;
    } else {
      idx += 1;
      picked = null;
      drawScoreDone = null;
    }
  }
</script>

<a class="back" href="/" use:link>← Home</a>

{#if done}
  <div class="center">
    {#if questions.length === 0}
      <h2>No mistakes to reinforce 🎉</h2>
      <p class="muted">Keep practicing — any wrong answers in Vocabulary or Review will show up here.</p>
    {:else}
      <h2>Great work! 💪</h2>
      <p class="muted">
        Answered {reinforcedCount} question{reinforcedCount === 1 ? '' : 's'}
        {#if cleared > 0} · Cleared {cleared} mistake{cleared === 1 ? '' : 's'}{/if}
      </p>
      <button class="primary" onclick={buildQuestions}>Another round</button>
    {/if}
    <a class="btn" href="/" use:link>← Home</a>
  </div>
{:else if !current}
  <div class="center muted">Loading…</div>
{:else if current.kind === 'draw'}
  <!-- ── Writing practice mistake ─────────────────────────────────── -->
  <div class="meta">
    Mistake {idx + 1} / {questions.length} · streak {current.mistake.streak}/3
  </div>
  <div class="draw-header">
    <div class="draw-prompt">
      <p class="quiz-hint">Draw this kanji:</p>
      <div class="draw-meaning">{current.kanji.meanings.slice(0, 3).join(', ')}</div>
    </div>
    <div class="peek-col">
      {#key current.mistake.id + '-peek'}
        <RevealKanji svg={current.kanji.svg} strokeCount={Math.min(3, current.kanji.strokes)} />
      {/key}
      <span class="peek-hint">max 3 peeks</span>
    </div>
  </div>

  {#key current.mistake.id + '-morph'}
    <PracticeMorph
      kanji={current.kanji}
      minimal={true}
      hideRefOnMount={true}
      onScore={onDrawScore}
    />
  {/key}

  {#if drawScoreDone !== null}
    <div class="answer-reveal">
      <div class="reveal-reading">
        {current.kanji.on.join('、') || '—'} · {current.kanji.kun.map((r) => r.replace(/[.\-]/g, '')).join('、') || '—'}
      </div>
      <div class="reveal-meaning">{current.kanji.meanings.join(', ')}</div>
      <div class="draw-score-line" class:ok={drawScoreDone >= 70} class:bad={drawScoreDone < 70}>
        Score: {drawScoreDone} / 100 · {drawScoreDone >= 70 ? 'passed ✓' : 'try again ✗'}
      </div>
    </div>
    <div class="actions single">
      <button class="primary" onclick={advance}>
        {idx + 1 >= questions.length ? 'Finish' : 'Next →'}
      </button>
    </div>
  {/if}
{:else}
  <!-- ── Choice-based mistake ─────────────────────────────────────── -->
  <div class="meta">
    Mistake {idx + 1} / {questions.length} · streak {current.mistake.streak}/3
  </div>
  <div class="card">
    <div class="big-prompt">{current.prompt}</div>
    {#if current.subPrompt}
      <div class="sub-prompt">{current.subPrompt}</div>
    {/if}
    <p class="quiz-hint">{current.instruction}</p>
  </div>

  <div class="choices">
    {#each current.choices as choice, i}
      <button
        class="choice-btn"
        class:correct={picked !== null && current.corrects.includes(choice)}
        class:wrong={picked !== null && i === picked && !current.corrects.includes(choice)}
        class:dimmed={picked !== null && !current.corrects.includes(choice) && i !== picked}
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
        {idx + 1 >= questions.length ? 'Finish' : 'Next →'}
      </button>
    </div>
  {/if}
{/if}

<style>
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); font-size: 0.9rem; }
  .center { padding: 2rem; text-align: center; }
  .center h2 { margin: 0.5rem 0; }
  .center .btn { display: inline-block; margin-top: 1rem; padding: 0.6rem 1.2rem; border-radius: 10px; border: 1px solid var(--border); color: var(--fg); text-decoration: none; }
  .meta { text-align: center; color: var(--fg-dim); font-size: 0.85rem; padding: 0.5rem; }
  .card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2rem 1.5rem;
    margin: 0.5rem 1rem;
    text-align: center;
    min-height: 10rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  .big-prompt { font-size: 2.5rem; font-family: 'Hiragino Mincho ProN', serif; }
  .sub-prompt { color: var(--accent); font-size: 1.1rem; }
  .quiz-hint { color: var(--fg-dim); font-size: 0.9rem; margin: 0.5rem 0 0; }
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
  .choice-btn.dimmed { opacity: 0.4; }
  .actions { display: flex; gap: 0.5rem; padding: 1rem; justify-content: center; }
  .actions.single button { min-width: 12rem; padding: 0.8rem 1.5rem; border-radius: 10px; border: 1px solid var(--border); background: var(--accent); color: #1b1b1f; font-weight: 600; cursor: pointer; }
  .muted { color: var(--fg-dim); }
  .primary { padding: 0.6rem 1.2rem; border-radius: 10px; border: 1px solid var(--accent); background: var(--accent); color: #1b1b1f; font-weight: 600; cursor: pointer; }

  /* Draw-mode styles (mirror Review.svelte) */
  .draw-header {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    padding: 0.75rem 1rem;
    max-width: 560px;
    margin: 0 auto;
  }
  .draw-prompt { flex: 1; min-width: 0; text-align: center; }
  .draw-meaning {
    font-size: 1.15rem;
    color: var(--accent);
    margin-top: 0.25rem;
  }
  .peek-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    flex-shrink: 0;
  }
  .peek-hint {
    color: var(--fg-dim);
    font-size: 0.7rem;
    letter-spacing: 0.03em;
  }
  .answer-reveal {
    text-align: center;
    padding: 0.75rem 1rem 0;
  }
  .reveal-reading {
    font-size: 1.2rem;
    color: var(--accent);
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
  }
  .reveal-meaning {
    font-size: 0.95rem;
    color: var(--fg);
    margin-top: 0.25rem;
  }
  .draw-score-line {
    font-size: 1rem;
    font-variant-numeric: tabular-nums;
    margin-top: 0.5rem;
  }
  .draw-score-line.ok { color: var(--ok); }
  .draw-score-line.bad { color: var(--err); }
</style>
