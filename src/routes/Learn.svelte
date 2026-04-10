<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import KanjiCanvas from '../lib/ui/KanjiCanvas.svelte';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import Furigana from '../lib/ui/Furigana.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { filterExamples, loadKnownKanji } from '../lib/data/known';
  import { exampleJp, type Example } from '../lib/data/types';
  import type { Point } from '../lib/stroke/compare';

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

  // Callouts for the morph step come pre-computed from the bundle pipeline —
  // each kanji carries up to 4 {word, reading, sentence} triples.
  const callouts = $derived(kanji?.callouts ?? []);

  type Step = 0 | 1 | 2;
  let step = $state<Step>(0);

  // Reset progression whenever the kanji changes.
  $effect(() => {
    void char;
    step = 0;
  });

  const STEPS = [
    { key: 'learn', label: 'Learn' },
    { key: 'practice', label: 'Practice' },
    { key: 'examples', label: 'Examples' },
  ] as const;

  function next() {
    if (step < 2) step = (step + 1) as Step;
  }
  function prev() {
    if (step > 0) step = (step - 1) as Step;
  }

  function speakReadings() {
    if (!kanji) return;
    const r = kanji.kun[0] ?? kanji.on[0] ?? kanji.char;
    speakJa(r);
  }

  // ── Learn → Practice stroke handoff ────────────────────────────────
  // When the user starts drawing on the Learn animation canvas, we capture
  // the stroke points. On pointerup we switch to Practice and pass the
  // stroke so PracticeMorph renders it instantly. A simple tap (< 5px
  // movement) also switches but without a pre-seeded stroke.
  const VB = 109; // must match KanjiCanvas / PracticeMorph viewBox
  let learnStroke = $state<Point[] | undefined>(undefined);
  let learnDrawing = $state(false); // true once the user drags — hides the animation SVG
  let _capturing = false;
  let _capturedPts: Point[] = [];
  let _capZone: HTMLDivElement | undefined;
  let _drawCanvas: HTMLCanvasElement | undefined;

  function _learnPt(e: PointerEvent): Point {
    if (!_capZone) return { x: 0, y: 0 };
    // The canvas is the first .wrap child inside the tap-zone.
    const wrap = _capZone.querySelector('.wrap') as HTMLElement | null;
    const rect = (wrap ?? _capZone).getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * VB,
      y: ((e.clientY - rect.top) / rect.height) * VB,
    };
  }

  function learnDown(e: PointerEvent) {
    _capturing = true;
    _capturedPts = [_learnPt(e)];
    try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch { /* ok */ }
    // Size the draw overlay to match the canvas area.
    if (_drawCanvas && _capZone) {
      const wrap = _capZone.querySelector('.wrap') as HTMLElement | null;
      if (wrap) {
        const sz = wrap.clientWidth;
        _drawCanvas.width = sz;
        _drawCanvas.height = sz;
      }
    }
  }

  function _renderLearnStroke() {
    if (!_drawCanvas || _capturedPts.length < 2) return;
    const ctx = _drawCanvas.getContext('2d');
    if (!ctx) return;
    const sx = _drawCanvas.width / VB;
    const sy = _drawCanvas.height / VB;
    ctx.clearRect(0, 0, _drawCanvas.width, _drawCanvas.height);
    ctx.strokeStyle = '#ff7a59';
    ctx.lineWidth = Math.max(4, _drawCanvas.width / 26);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(_capturedPts[0].x * sx, _capturedPts[0].y * sy);
    for (let i = 1; i < _capturedPts.length; i++) {
      ctx.lineTo(_capturedPts[i].x * sx, _capturedPts[i].y * sy);
    }
    ctx.stroke();
  }

  function learnMove(e: PointerEvent) {
    if (!_capturing) return;
    _capturedPts.push(_learnPt(e));
    if (!learnDrawing) learnDrawing = true;
    _renderLearnStroke();
  }

  function learnUp() {
    if (!_capturing) return;
    _capturing = false;
    if (_capturedPts.length >= 2) {
      learnStroke = _capturedPts;
    } else {
      learnStroke = undefined;
    }
    _capturedPts = [];
    learnDrawing = false;
    step = 1 as Step;
  }
</script>

<a class="back" href="/" use:link>← Back</a>

{#if !kanji}
  <div class="center">Unknown kanji: {char}</div>
{:else}
  <header class="head">
    <div class="kanji-hero">
      <span class="kanji-glyph">{kanji.char}</span>
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
      <!-- Step 1: Learn — animation + readings + TTS -->
      <div class="learn-step">
        <h2>Watch the stroke order</h2>
        <p class="hint">Each stroke is drawn in order. Tap the canvas when you're ready to practice.</p>
        <div class="stroke-info"><b>{kanji.strokes}</b> strokes</div>
        <!-- Touching the canvas area captures a stroke and switches to Practice -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="canvas-tap-zone"
          class:drawing={learnDrawing}
          bind:this={_capZone}
          onpointerdown={learnDown}
          onpointermove={learnMove}
          onpointerup={learnUp}
          onpointercancel={learnUp}
        >
          {#key char + 'animate'}
            <KanjiCanvas svg={kanji.svg} mode="animate" />
          {/key}
          <canvas class="draw-overlay" bind:this={_drawCanvas}></canvas>
        </div>
        <div class="readings-grid">
          <div class="reading-block">
            <div class="reading-label">On'yomi</div>
            <div class="reading-vals">
              {#each kanji.on as r}
                <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>
                  <span>{r}</span> <span class="speaker">🔊</span>
                </button>
              {/each}
              {#if !kanji.on.length}<span class="muted">—</span>{/if}
            </div>
          </div>
          <div class="reading-block">
            <div class="reading-label">Kun'yomi</div>
            <div class="reading-vals">
              {#each kanji.kun as r}
                <button class="chip" onclick={() => speakJa(r)} disabled={!ttsSupported()}>
                  <span>{r}</span> <span class="speaker">🔊</span>
                </button>
              {/each}
              {#if !kanji.kun.length}<span class="muted">—</span>{/if}
            </div>
          </div>
        </div>
        <button class="primary big" onclick={speakReadings} disabled={!ttsSupported()}>
          🔊 Hear it
        </button>
      </div>
    {:else if step === 1}
      <!-- Step 2: Practice — free-form drawing with morph -->
      <div class="practice">
        <h2>Draw it from memory</h2>
        <p class="hint">Draw any way you like — when you're done, your strokes will morph into the real shape.</p>
        {#key char + 'morph'}
          <PracticeMorph {kanji} {callouts} {knownKanji} initialStroke={learnStroke} />
        {/key}
      </div>
    {:else}
      <!-- Step 3: Examples with furigana + TTS -->
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
                  >🔊</button>
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
    {#if step < 2}
      <button onclick={prev} disabled={step === 0}>← Back</button>
      <button class="primary" onclick={next}>Next →</button>
    {:else}
      <button onclick={prev}>← Back</button>
      <a class="btn home-btn" href="/" use:link>🏠 Home</a>
      {#if words.length}
        <a class="btn primary" href={`/vocab/${encodeURIComponent(words[0].id)}`} use:link>Vocab →</a>
      {/if}
    {/if}
  </div>

  {#if step === 2 && words.length > 1}
    <section class="words-section">
      <h3>Words using {kanji.char}</h3>
      <div class="word-grid">
        {#each words.slice(0, 12) as w (w.id)}
          <a class="word-card" href={`/vocab/${encodeURIComponent(w.id)}`} use:link>
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
    grid-template-columns: repeat(3, 1fr);
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
  .hint {
    text-align: center;
    color: var(--fg-dim);
    margin: 0 0 1rem;
    font-size: 0.9rem;
  }

  .learn-step .readings-grid {
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
  .learn-step .primary.big {
    display: block;
    width: 100%;
    margin-top: 1rem;
    padding: 1rem;
    font-size: 1.05rem;
  }
  /* Matches PracticeMorph's .hint-row height so the canvas sits at the
     same vertical position on both Learn and Practice steps. */
  .stroke-info {
    text-align: center;
    margin-bottom: 0.75rem;
    color: var(--fg);
    font-size: 1.05rem;
  }
  .canvas-tap-zone {
    cursor: pointer;
    position: relative;
  }
  /* When the user starts drawing, hide the kanji stroke paths but keep the
     canvas background + grid visible so they have a drawing surface. */
  .canvas-tap-zone.drawing :global(svg g) {
    opacity: 0;
    transition: opacity 0.12s;
  }
  /* Transparent overlay canvas that renders the user's stroke in real-time. */
  .draw-overlay {
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: none;
    z-index: 2;
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
    .learn-step .readings-grid {
      grid-template-columns: 1fr;
    }
    .step .lbl {
      font-size: 0.7rem;
    }
  }
</style>
