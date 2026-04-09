<script lang="ts">
  import { link, push } from 'svelte-spa-router';
  import { onMount } from 'svelte';
  import { bundle } from '../lib/data/bundle';
  import { dueSrs, putSrs, getSrs, getAllBestScores } from '../lib/data/db';
  import { grade, newCard } from '../lib/srs/sm2';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { KNOWN_THRESHOLD } from '../lib/data/known';
  import type { Grade, SrsState } from '../lib/data/types';

  const NEW_PER_SESSION = 10;

  let queue = $state<SrsState[]>([]);
  let idx = $state(0);
  let showBack = $state(false);
  let done = $state(false);

  async function buildQueue() {
    const now = Date.now();
    const due = await dueSrs(now, 200);

    // Top up with new cards for kanji/words the user has already mastered
    // (score >= 80) but hasn't been quizzed on via SRS yet.
    if (due.length < NEW_PER_SESSION) {
      const b = bundle();
      const scores = await getAllBestScores();
      const need = NEW_PER_SESSION - due.length;
      const newCandidates: SrsState[] = [];
      for (const k of Object.values(b.kanji)) {
        if (newCandidates.length >= need) break;
        if ((scores.get(k.char) ?? 0) < KNOWN_THRESHOLD) continue;
        const id = `kanji:${k.char}`;
        if (!(await getSrs(id))) newCandidates.push(newCard(id, 'kanji', now));
      }
      for (const w of Object.values(b.words)) {
        if (newCandidates.length >= need) break;
        if (w.kanji.length > 0 && !w.kanji.every((c) => (scores.get(c) ?? 0) >= KNOWN_THRESHOLD)) continue;
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

  async function answer(g: Grade) {
    if (!current) return;
    const next = grade(current, g);
    await putSrs(next);
    if (idx + 1 >= queue.length) {
      done = true;
    } else {
      idx += 1;
      showBack = false;
    }
  }
</script>

<a class="back" href="/" use:link>← Back</a>

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
      {#if showBack}
        <div class="back-body">
          <div class="readings">
            <div><span class="lbl">On</span> {display.kanji.on.join('、') || '—'}</div>
            <div><span class="lbl">Kun</span> {display.kanji.kun.join('、') || '—'}</div>
          </div>
          <div class="en">{display.kanji.meanings.join(', ')}</div>
          <button onclick={() => speakJa([...display.kanji.on, ...display.kanji.kun][0] ?? display.kanji.char)} disabled={!ttsSupported()}>🔊</button>
        </div>
      {/if}
    {:else if display.kind === 'word' && display.word}
      <div class="word-front">{display.word.jp}</div>
      {#if showBack}
        <div class="back-body">
          <div class="reading">{display.word.reading}</div>
          <div class="en">{display.word.meanings.join('; ')}</div>
          <button onclick={() => speakJa(display.word.jp)} disabled={!ttsSupported()}>🔊</button>
        </div>
      {/if}
    {/if}
  </div>

  {#if !showBack}
    <div class="actions single">
      <button class="primary" onclick={() => (showBack = true)}>Show answer</button>
    </div>
  {:else}
    <div class="actions grade">
      <button onclick={() => answer('again')}>Again</button>
      <button onclick={() => answer('hard')}>Hard</button>
      <button class="primary" onclick={() => answer('good')}>Good</button>
      <button onclick={() => answer('easy')}>Easy</button>
    </div>
  {/if}

  {#if display.kind === 'kanji' && display.kanji}
    <div class="jump">
      <a href={`/learn/${encodeURIComponent(display.kanji.char)}`} use:link onclick={() => push('/learn/' + encodeURIComponent(display.kanji.char))}>Open lesson →</a>
    </div>
  {:else if display.kind === 'word' && display.word}
    <div class="jump">
      <a href={`/vocab/${encodeURIComponent(display.word.id)}`} use:link>Open card →</a>
    </div>
  {/if}
{/if}

<style>
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); }
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
  .actions { display: flex; gap: 0.5rem; padding: 1rem; justify-content: center; }
  .actions.grade button { flex: 1; max-width: 7rem; }
  .actions.single button { min-width: 12rem; }
  .jump { text-align: center; padding: 0.5rem 1rem 2rem; }
  .muted { color: var(--fg-dim); }
</style>
