<script lang="ts">
  import { link } from 'svelte-spa-router';
  import Furigana from '../lib/ui/Furigana.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { kanaMatchScore, recognizeJa, sttSupported } from '../lib/speech/stt';

  interface Params {
    id: string;
  }
  const { params }: { params: Params } = $props();
  const word = $derived(bundle().words[decodeURIComponent(params.id)]);

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

<a class="back" href="/" use:link>← Back</a>

{#if !word}
  <div class="center">Unknown word.</div>
{:else}
  <article>
    <header>
      <ruby class="jp">
        {word.jp}
        <rt>{word.reading}</rt>
      </ruby>
      <div class="pos">{word.pos.join(', ')}</div>
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

    {#if word.examples.length}
      <section>
        <h2>Examples</h2>
        <ul class="examples">
          {#each word.examples as ex (ex.jp)}
            <li class="example-card">
              <button class="sentence" onclick={() => speakJa(ex.jp)} aria-label="Speak sentence">
                <Furigana segments={ex.segs} />
                <span class="speak-tag">🔊</span>
              </button>
              <div class="ex-en">{ex.en}</div>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  </article>
{/if}

<style>
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); }
  .center { padding: 2rem; text-align: center; color: var(--fg-dim); }
  article { padding: 0 1rem 2rem; }
  header { text-align: center; padding: 0.5rem 0 1rem; }
  .jp { font-size: 3rem; font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif; }
  .jp rt { font-size: 1rem; color: var(--fg-dim); }
  .pos { color: var(--fg-dim); font-size: 0.85rem; margin-top: 0.25rem; }
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
  .sentence {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    background: transparent;
    border: none;
    color: var(--fg);
    text-align: left;
    padding: 0;
    font-size: 1.15rem;
  }
  .speak-tag {
    flex-shrink: 0;
    font-size: 0.9rem;
    opacity: 0.7;
    margin-top: 0.4rem;
  }
  .ex-en {
    color: var(--fg-dim);
    font-size: 0.9rem;
    margin-top: 0.5rem;
    text-align: left;
    line-height: 1.35;
  }
</style>
