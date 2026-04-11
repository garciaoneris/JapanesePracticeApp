<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import Furigana from '../lib/ui/Furigana.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { kanaMatchScore, recognizeJa, sttSupported } from '../lib/speech/stt';
  import { filterExamples, loadKnownKanji } from '../lib/data/known';
  import { exampleJp } from '../lib/data/types';

  interface Params {
    id: string;
  }
  const { params }: { params: Params } = $props();
  const word = $derived(bundle().words[decodeURIComponent(params.id)]);

  // Known-kanji filter for the example list. The word's own kanji are always
  // treated as "known" while viewing its page — you're looking at them right now.
  let knownKanji = $state<Set<string>>(new Set());
  /** If the user came here from a Learn page word grid, remember the kanji
   *  so we can show a "Back to 山" link. */
  let learnKanji = $state<string | null>(null);
  onMount(async () => {
    knownKanji = await loadKnownKanji();
    learnKanji = sessionStorage.getItem('vocab-from-learn');
    sessionStorage.removeItem('vocab-from-learn');
  });

  const filteredExamples = $derived.by(() => {
    if (!word) return { kept: [], tooAdvanced: false };
    const effective = new Set(knownKanji);
    for (const ch of word.kanji) effective.add(ch);
    return filterExamples(word.examples, effective);
  });
  const exampleList = $derived(filteredExamples.kept);
  const exampleTooAdvanced = $derived(filteredExamples.tooAdvanced);

  let listening = $state(false);
  let heard = $state<string>('');
  let score = $state<number | null>(null);
  let sttError = $state<string>('');

  async function tryStt() {
    if (!word) return;
    sttError = '';
    heard = '';
    score = null;
    listening = true;
    try {
      const r = await recognizeJa();
      heard = r.transcript;
      score = kanaMatchScore(word.reading, r.transcript);
    } catch (e) {
      sttError = e instanceof Error ? e.message : String(e);
    } finally {
      listening = false;
    }
  }
</script>

<div class="nav-links">
  <a class="back" href="/" use:link>← Home</a>
  <a class="back" href="/vocabulary" use:link>← Vocabulary</a>
  {#if learnKanji}
    <a class="back" href={`/learn/${encodeURIComponent(learnKanji)}`} use:link>← Back to {learnKanji}</a>
  {/if}
  {#if word?.kanji?.length}
    <button class="back back-btn" onclick={() => { sessionStorage.setItem('vocab-open-kanji', word.kanji[0]); window.location.hash = '#/vocabulary'; }}>← {word.kanji[0]} words</button>
  {/if}
</div>

{#if !word}
  <div class="center">Unknown word.</div>
{:else}
  <article>
    <header>
      <ruby class="jp">
        {word.jp}
        <rt>{word.reading}</rt>
      </ruby>
    </header>

    <p class="en">{word.meanings.join('; ')}</p>

    <div class="actions">
      <button class="primary" onclick={() => speakJa(word.jp)} disabled={!ttsSupported()}>🔊 Speak</button>
      <button onclick={tryStt} disabled={listening || !sttSupported()}>
        {listening ? '🎙 Listening…' : '🎙 Speak it back'}
      </button>
    </div>

    {#if heard}
      <div class="stt">
        <div>Heard: <b>{heard}</b></div>
        <div>Target: {word.reading}</div>
        {#if score !== null}
          <div class="score" class:ok={score >= 0.8} class:bad={score < 0.5}>
            Match: {(score * 100).toFixed(0)}%
          </div>
        {/if}
      </div>
    {/if}
    {#if sttError}
      <div class="err">STT: {sttError}</div>
    {/if}

    {#if word.kanji.length}
      <section>
        <h2>Kanji</h2>
        <div class="krow">
          {#each word.kanji as ch}
            <a class="kcell" href={`/learn/${encodeURIComponent(ch)}`} use:link>{ch}</a>
          {/each}
        </div>
      </section>
    {/if}

    {#if exampleList.length}
      <section>
        <h2>Examples</h2>
        {#if exampleTooAdvanced}
          <p class="advanced-hint">
            These sentences include kanji you haven't mastered yet.
          </p>
        {/if}
        <ul class="examples">
          {#each exampleList as ex (exampleJp(ex))}
            <li class="example-card">
              <div class="ex-row">
                <div
                  class="sentence"
                  onclick={() => speakJa(exampleJp(ex))}
                  onkeydown={(e) => e.key === 'Enter' && speakJa(exampleJp(ex))}
                  role="button"
                  tabindex="0"
                  aria-label="Tap empty space to hear the whole sentence"
                >
                  <Furigana
                    segments={ex.segs}
                    knownKanji={knownKanji}
                    currentKanji={word.kanji[0]}
                  />
                </div>
                <button
                  class="speak-btn"
                  onclick={(e) => { e.stopPropagation(); speakJa(exampleJp(ex)); }}
                  aria-label="Speak whole sentence"
                >🔊</button>
              </div>
              <div class="ex-en">{ex.en}</div>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  </article>
{/if}

<style>
  .nav-links { display: flex; gap: 0.25rem; flex-wrap: wrap; }
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); font-size: 0.9rem; }
  .back-btn { background: none; border: none; cursor: pointer; font-family: inherit; }
  .center { padding: 2rem; text-align: center; color: var(--fg-dim); }
  article { padding: 0 1rem 2rem; }
  header { text-align: center; padding: 0.5rem 0 1rem; }
  .jp { font-size: 3rem; font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif; }
  .jp rt { font-size: 1rem; color: var(--fg-dim); }
  .en { text-align: center; font-size: 1.1rem; margin: 0.5rem 0 1rem; }
  .actions { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; }
  .stt {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    text-align: center;
  }
  .score { margin-top: 0.4rem; font-weight: 600; }
  .score.ok { color: var(--ok); }
  .score.bad { color: var(--err); }
  .err { color: var(--err); text-align: center; margin-top: 0.5rem; font-size: 0.85rem; }
  h2 { font-size: 0.85rem; text-transform: uppercase; color: var(--fg-dim); letter-spacing: 0.08em; margin: 1.5rem 0 0.5rem; }
  .krow { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .kcell {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 3rem;
    height: 3rem;
    font-size: 1.8rem;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--fg);
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
  }
  .advanced-hint {
    background: rgba(255, 210, 74, 0.1);
    border: 1px solid rgba(255, 210, 74, 0.3);
    color: #ffd24a;
    padding: 0.65rem 0.85rem;
    border-radius: 10px;
    font-size: 0.85rem;
    margin: 0 0 0.85rem;
    text-align: center;
  }
  .examples { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.7rem; }
  .example-card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem;
    transition: border-color 0.15s;
  }
  .example-card:hover {
    border-color: rgba(255, 122, 89, 0.4);
  }
  .ex-row {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }
  .sentence {
    flex: 1;
    min-width: 0;
    color: var(--fg);
    font-size: 1.15rem;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .sentence:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; border-radius: 4px; }
  .speak-btn {
    flex-shrink: 0;
    padding: 0.35rem 0.6rem;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 0.95rem;
    opacity: 0.75;
  }
  .speak-btn:hover { opacity: 1; border-color: var(--accent); }
  .ex-en {
    color: var(--fg-dim);
    font-size: 0.9rem;
    margin-top: 0.5rem;
    text-align: left;
    line-height: 1.35;
  }
</style>
