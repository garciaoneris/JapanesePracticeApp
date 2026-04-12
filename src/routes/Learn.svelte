<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import Furigana from '../lib/ui/Furigana.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { filterExamples, loadKnownKanji } from '../lib/data/known';
  import { exampleJp, type Example } from '../lib/data/types';

  interface Params {
    char: string;
  }
  const { params }: { params: Params } = $props();

  const char = $derived(decodeURIComponent(params.char));
  const kanji = $derived(bundle().kanji[char]);
  const words = $derived(kanji ? kanji.words.map((id) => bundle().words[id]).filter(Boolean) : []);

  // Set of kanji the learner has mastered (best score >= 80). Loaded on
  // mount; the filtered-examples $derived picks it up reactively.
  let knownKanji = $state<Set<string>>(new Set());
  onMount(async () => {
    knownKanji = await loadKnownKanji();
  });

  // Pull up to 8 unique example sentences from the kanji's vocab, then filter
  // them through the known-kanji gate (treating the current kanji as known).
  // If the gate removes everything, the fallback pair surfaces with a hint.
  const examplesRaw = $derived.by<Example[]>(() => {
    const out: Example[] = [];
    const seen = new Set<string>();
    for (const w of words) {
      for (const ex of w.examples) {
        if (seen.has(exampleJp(ex))) continue;
        seen.add(exampleJp(ex));
        out.push(ex);
        if (out.length >= 8) return out;
      }
      if (out.length >= 8) return out;
    }
    return out;
  });

  const filteredExamples = $derived(filterExamples(examplesRaw, knownKanji, char));
  const examples = $derived(filteredExamples.kept.slice(0, 4));
  const tooAdvanced = $derived(filteredExamples.tooAdvanced);

  // Callouts for the morph step come pre-computed from the bundle pipeline --
  // each kanji carries up to 4 {word, reading, sentence} triples.
  const callouts = $derived(kanji?.callouts ?? []);

  const STEPS = [
    { key: 'practice', label: 'Practice' },
    { key: 'examples', label: 'Examples' },
  ] as const;
  type Step = 0 | 1;
  let step = $state<Step>(0);

  // Reset progression whenever the kanji changes.
  $effect(() => {
    void char;
    step = 0;
  });

  function next() {
    if (step < 1) step = (step + 1) as Step;
  }
  function prev() {
    if (step > 0) step = (step - 1) as Step;
  }

  function speakReadings() {
    if (!kanji) return;
    const r = kanji.kun[0] ?? kanji.on[0] ?? kanji.char;
    speakJa(r);
  }

  /** Bound to PracticeMorph — true while the reference animation is visible,
   *  false once the user starts drawing. Controls whether the hero shows the
   *  plain glyph (visible) or the RevealKanji peek mode (hidden). */
  let showingRef = $state(true);
</script>

<a class="back" href="/" use:link>← Back</a>

{#if !kanji}
  <div class="center">Unknown kanji: {char}</div>
{:else}
  <header class="head">
    <div class="kanji-hero">
      {#if showingRef || step === 1}
        <span class="kanji-glyph">{kanji.char}</span>
      {:else}
        {#key char}
          <RevealKanji svg={kanji.svg} strokeCount={kanji.strokes} />
        {/key}
      {/if}
      <div class="hero-meta">
        <div class="badges">
          <span class="badge n">N{kanji.jlpt}</span>
          <span class="badge">{kanji.strokes} strokes</span>
        </div>
        <p class="meaning">{kanji.meanings.slice(0, 3).join(' · ')}</p>
      </div>
    </div>
  </header>

  <nav class="stepper" aria-label="Lesson steps">
    {#each STEPS as s, i}
      <button
        class="step"
        class:active={step === i}
        class:done={step > i}
        onclick={() => (step = i as Step)}
      >
        <span class="num">{i + 1}</span>
        <span class="lbl">{s.label}</span>
      </button>
    {/each}
  </nav>

  <section class="panel">
    {#if step === 0}
      <!-- Step 0: Practice — single canvas with animation + drawing -->
      <div class="practice-step">
        {#key char + 'morph'}
          <PracticeMorph {kanji} {callouts} {knownKanji} onRefChange={(v) => (showingRef = v)} />
        {/key}

        <div class="readings-grid">
          <div class="reading-block">
            <div class="reading-label">On'yomi</div>
            <div class="reading-vals">
              {#each kanji.on as r}
                <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>
                  <span>{r}</span> <span class="speaker">&#x1f50a;</span>
                </button>
              {/each}
              {#if !kanji.on.length}<span class="muted">--</span>{/if}
            </div>
          </div>
          <div class="reading-block">
            <div class="reading-label">Kun'yomi</div>
            <div class="reading-vals">
              {#each kanji.kun as r}
                <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>
                  <span>{r}</span> <span class="speaker">&#x1f50a;</span>
                </button>
              {/each}
              {#if !kanji.kun.length}<span class="muted">--</span>{/if}
            </div>
          </div>
        </div>
      </div>
    {:else}
      <!-- Step 1: Examples with furigana + TTS -->
      <div class="examples">
        <h2>See it in context</h2>
        {#if tooAdvanced && examples.length > 0}
          <p class="advanced-hint">
            These sentences include kanji you haven't mastered yet. Keep practicing and they'll clear up.
          </p>
        {/if}
        {#if examples.length === 0}
          <p class="muted">No example sentences for this kanji yet.</p>
        {:else}
          <ul>
            {#each examples as ex (exampleJp(ex))}
              <li class="example-card">
                <div class="ex-row">
                  <div
                    class="ex-jp"
                    onclick={() => speakJa(exampleJp(ex))}
                    onkeydown={(e) => e.key === 'Enter' && speakJa(exampleJp(ex))}
                    role="button"
                    tabindex="0"
                    aria-label="Tap empty space to hear the whole sentence"
                  >
                    <Furigana segments={ex.segs} knownKanji={knownKanji} currentKanji={char} />
                  </div>
                  <button
                    class="speak-btn"
                    onclick={(e) => { e.stopPropagation(); speakJa(exampleJp(ex)); }}
                    aria-label="Speak whole sentence"
                  >&#x1f50a;</button>
                </div>
                <div class="ex-en">{ex.en}</div>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
  </section>

  <div class="nav-row">
    <button onclick={prev} disabled={step === 0}>← Back</button>
    <a class="btn home-btn" href="/" use:link>&#x1f3e0; Home</a>
    {#if step === 0}
      <button class="primary" onclick={next}>Next →</button>
    {:else if words.length}
      <a class="btn primary" href={`/vocab/${encodeURIComponent(words[0].id)}`} use:link>Vocab →</a>
    {/if}
  </div>

  {#if step === 1 && words.length > 1}
    <section class="words-section">
      <h3>Words using {kanji.char}</h3>
      <div class="word-grid">
        {#each words.slice(0, 12) as w (w.id)}
          <a class="word-card" href={`/vocab/${encodeURIComponent(w.id)}`} use:link
             onclick={() => sessionStorage.setItem('vocab-from-learn', char)}>
            <div class="w-jp">{w.jp}</div>
            <div class="w-reading">{w.reading}</div>
            <div class="w-en">{w.meanings[0] ?? ''}</div>
          </a>
        {/each}
      </div>
    </section>
  {/if}
{/if}

<style>
  .back {
    display: inline-block;
    padding: 0.75rem 1rem;
    color: var(--fg-dim);
    font-size: 0.9rem;
  }
  .center {
    padding: 2rem;
    text-align: center;
    color: var(--fg-dim);
  }

  .head {
    padding: 0.5rem 1rem 1rem;
  }
  .kanji-hero {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    background: linear-gradient(135deg, rgba(255, 122, 89, 0.18), rgba(255, 122, 89, 0.04));
    padding: 1.25rem 1.5rem;
    border-radius: 20px;
    border: 1px solid rgba(255, 122, 89, 0.25);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
    /* Fixed height prevents layout shift when toggling glyph ↔ RevealKanji */
    min-height: 6.5rem;
  }
  .kanji-glyph {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    font-size: clamp(4.5rem, 18vw, 7.5rem);
    line-height: 1;
    color: var(--fg);
    text-shadow: 0 4px 24px rgba(255, 122, 89, 0.35);
  }
  .hero-meta {
    flex: 1;
    min-width: 0;
  }
  .badges {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.4rem;
  }
  .badge {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border);
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    color: var(--fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .badge.n {
    background: var(--accent);
    color: #1b1b1f;
    border-color: var(--accent);
    font-weight: 700;
  }
  .meaning {
    margin: 0.2rem 0 0;
    color: var(--fg);
    font-size: 1.05rem;
    font-weight: 500;
  }

  .stepper {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.4rem;
    padding: 0.5rem 1rem 0;
  }
  .step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 0.6rem 0.4rem;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--fg-dim);
    font-size: 0.75rem;
    transition: all 0.2s;
  }
  .step .num {
    width: 1.6rem;
    height: 1.6rem;
    border-radius: 50%;
    background: var(--border);
    display: grid;
    place-items: center;
    font-weight: 700;
    color: var(--fg);
    font-size: 0.85rem;
  }
  .step.active {
    border-color: var(--accent);
    background: rgba(255, 122, 89, 0.12);
    color: var(--fg);
  }
  .step.active .num {
    background: var(--accent);
    color: #1b1b1f;
  }
  .step.done .num {
    background: var(--ok);
    color: #1b1b1f;
  }
  .step.done {
    color: var(--fg);
  }

  .panel {
    padding: 1rem;
    min-height: 22rem;
  }
  .panel h2 {
    text-align: center;
    margin: 0 0 0.25rem;
    font-size: 1.2rem;
    font-weight: 600;
  }

  .practice-step .readings-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-top: 1rem;
  }
  .reading-block {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0.85rem 1rem;
  }
  .reading-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    margin-bottom: 0.5rem;
    font-weight: 600;
  }
  .reading-vals {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    background: rgba(255, 122, 89, 0.15);
    border-color: rgba(255, 122, 89, 0.4);
    font-size: 1rem;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui;
  }
  .chip .speaker {
    font-size: 0.7rem;
    opacity: 0.7;
  }

  .nav-row {
    display: flex;
    gap: 0.5rem;
    padding: 0 1rem 1rem;
    justify-content: space-between;
  }
  .nav-row button,
  .nav-row .btn {
    flex: 1;
    padding: 0.85rem;
    font-size: 1rem;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-alt);
    color: var(--fg);
    text-decoration: none;
  }
  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #1b1b1f;
    font-weight: 600;
  }
  .home-btn {
    flex: 0.8;
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
  .examples ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }
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
  .ex-jp {
    flex: 1;
    min-width: 0;
    color: var(--fg);
    font-size: 1.15rem;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .ex-jp:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; border-radius: 4px; }
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
    line-height: 1.35;
  }

  .words-section {
    padding: 0.5rem 1rem 2.5rem;
  }
  .words-section h3 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    margin: 0 0 0.75rem;
    font-weight: 600;
  }
  .word-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.5rem;
  }
  .word-card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.75rem;
    color: var(--fg);
    text-decoration: none;
    transition: border-color 0.15s, transform 0.15s;
  }
  .word-card:active {
    transform: scale(0.97);
  }
  .w-jp {
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.3rem;
  }
  .w-reading {
    color: var(--fg-dim);
    font-size: 0.8rem;
    margin-top: 0.15rem;
  }
  .w-en {
    color: var(--fg);
    font-size: 0.8rem;
    margin-top: 0.35rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .muted { color: var(--fg-dim); }

  @media (max-width: 380px) {
    .practice-step .readings-grid {
      grid-template-columns: 1fr;
    }
    .step .lbl {
      font-size: 0.7rem;
    }
  }
</style>
