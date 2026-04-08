<script lang="ts">
  import { link } from 'svelte-spa-router';
  import KanjiCanvas from '../lib/ui/KanjiCanvas.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';

  interface Params {
    char: string;
  }
  const { params }: { params: Params } = $props();

  const char = $derived(decodeURIComponent(params.char));
  const kanji = $derived(bundle().kanji[char]);
  const words = $derived(kanji ? kanji.words.map((id) => bundle().words[id]).filter(Boolean) : []);
</script>

<a class="back" href="/" use:link>← Back</a>

{#if !kanji}
  <div class="center">Unknown kanji: {char}</div>
{:else}
  <div class="head">
    <h1 class="kanji-big">{kanji.char}</h1>
    <div class="meta">
      <span class="tag">N{kanji.jlpt}</span>
      <span class="tag">{kanji.strokes} strokes</span>
    </div>
  </div>

  <section class="readings">
    <div class="row">
      <span class="lbl">On</span>
      <span class="vals">
        {#each kanji.on as r}
          <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>{r}</button>
        {/each}
        {#if !kanji.on.length}<span class="muted">—</span>{/if}
      </span>
    </div>
    <div class="row">
      <span class="lbl">Kun</span>
      <span class="vals">
        {#each kanji.kun as r}
          <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>{r}</button>
        {/each}
        {#if !kanji.kun.length}<span class="muted">—</span>{/if}
      </span>
    </div>
    <div class="row">
      <span class="lbl">Meaning</span>
      <span class="vals en">{kanji.meanings.join(', ')}</span>
    </div>
  </section>

  <section class="practice">
    <h2>Practice strokes</h2>
    {#key char}
      <KanjiCanvas svg={kanji.svg} />
    {/key}
  </section>

  {#if words.length}
    <section>
      <h2>Words using {kanji.char}</h2>
      <ul class="words">
        {#each words as w (w.id)}
          <li>
            <a href={`/vocab/${encodeURIComponent(w.id)}`} use:link>
              <span class="jp">{w.jp}</span>
              <span class="muted">{w.reading}</span>
              <span class="en">{w.meanings.slice(0, 2).join('; ')}</span>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
{/if}

<style>
  .back { display: inline-block; padding: 0.75rem 1rem; color: var(--fg-dim); }
  .center { padding: 2rem; text-align: center; color: var(--fg-dim); }
  .head { text-align: center; padding: 1rem 1rem 0.5rem; }
  .meta { display: flex; gap: 0.5rem; justify-content: center; margin-top: 0.5rem; }
  .tag { background: var(--bg-alt); border: 1px solid var(--border); padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.8rem; color: var(--fg-dim); }
  .readings { padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem; }
  .row { display: flex; gap: 0.75rem; align-items: baseline; }
  .lbl { width: 4rem; color: var(--fg-dim); font-size: 0.85rem; text-transform: uppercase; }
  .vals { display: flex; flex-wrap: wrap; gap: 0.35rem; flex: 1; }
  .chip { padding: 0.25rem 0.7rem; border-radius: 999px; font-size: 0.95rem; }
  .en { color: var(--fg); }
  .muted { color: var(--fg-dim); }
  .practice { padding: 0.5rem 1rem 1.5rem; }
  h2 { font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-dim); margin: 0 0 0.75rem; text-align: center; }
  .words { list-style: none; padding: 0 1rem 2rem; margin: 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .words a {
    display: grid;
    grid-template-columns: auto auto 1fr;
    gap: 0.75rem;
    padding: 0.6rem 0.8rem;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--fg);
    align-items: baseline;
  }
  .jp { font-size: 1.2rem; }
</style>
