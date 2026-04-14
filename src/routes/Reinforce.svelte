<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { speakJa } from '../lib/speech/tts';
  import { getMistakes, reinforceCorrect, reinforceWrong, type Mistake } from '../lib/data/mistakes';

  type Question = {
    mistake: Mistake;
    prompt: string;        // shown as the question (kanji or kanji+reading)
    subPrompt?: string;    // e.g. the reading for meaning questions
    instruction: string;   // "What is the reading?" / "What does this mean?"
    choices: string[];
    correct: string;
    speakText: string;     // what to speak aloud after answering
  };

  let mistakes = $state<Mistake[]>([]);
  let questions = $state<Question[]>([]);
  let idx = $state(0);
  let picked = $state<number | null>(null);
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
        prompt: k.char,
        instruction: 'What does this mean?',
        choices,
        correct,
        speakText: k.kun[0] ?? k.on[0] ?? k.char,
      };
    }
    // word-reading or word-meaning
    const w = b.words[m.id];
    if (!w) return null;
    if (m.type === 'word-reading') {
      const correct = w.reading;
      const pool: string[] = [];
      for (const other of Object.values(b.words)) {
        if (other.reading && other.reading !== correct) pool.push(other.reading);
      }
      const distractors = shuffle(pool).slice(0, 3);
      const choices = shuffle([correct, ...distractors]);
      return {
        mistake: m,
        prompt: w.jp,
        instruction: 'What is the reading?',
        choices,
        correct,
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
      prompt: w.jp,
      subPrompt: w.reading,
      instruction: 'What does this mean?',
      choices,
      correct,
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
    done = questions.length === 0;
    cleared = 0;
    reinforcedCount = 0;
  }

  onMount(buildQuestions);

  const current = $derived(questions[idx]);

  async function pickChoice(i: number) {
    if (picked !== null || !current) return;
    picked = i;
    const isCorrect = current.choices[i] === current.correct;
    if (isCorrect) {
      // Check if this would clear the mistake (streak would reach REINFORCE_CLEAR_STREAK)
      const before = current.mistake.streak;
      await reinforceCorrect(current.mistake.type, current.mistake.id);
      if (before + 1 >= 3) cleared++;
      reinforcedCount++;
    } else {
      await reinforceWrong(current.mistake.type, current.mistake.id);
    }
    // Speak the reading / word aloud
    speakJa(current.speakText);
  }

  function advance() {
    if (idx + 1 >= questions.length) {
      done = true;
    } else {
      idx += 1;
      picked = null;
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
{:else}
  <div class="meta">
    Mistake {idx + 1} / {questions.length}
    · streak {current.mistake.streak}/3
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
        class:correct={picked !== null && choice === current.correct}
        class:wrong={picked !== null && i === picked && choice !== current.correct}
        class:dimmed={picked !== null && choice !== current.correct && i !== picked}
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
</style>
