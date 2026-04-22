<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { link } from 'svelte-spa-router';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import Furigana from '../lib/ui/Furigana.svelte';
  import Petal from '../lib/ui/Petal.svelte';
  import Blossom from '../lib/ui/Blossom.svelte';
  import PetalField from '../lib/ui/PetalField.svelte';
  import { bundle } from '../lib/data/bundle';
  import { speakJa, ttsSupported } from '../lib/speech/tts';
  import { filterExamples, loadKnownKanji } from '../lib/data/known';
  import { exampleJp, type Example } from '../lib/data/types';
  import { getBestScore } from '../lib/data/db';
  import { startTick, stopTick } from '../lib/gamification/goal';

  interface Params {
    char: string;
  }
  const { params }: { params: Params } = $props();

  const char = $derived(decodeURIComponent(params.char));
  const kanji = $derived(bundle().kanji[char]);
  const words = $derived(kanji ? kanji.words.map((id) => bundle().words[id]).filter(Boolean) : []);

  /** JLPT (5..0) → curriculum level (1..5). Same mapping as Home / Review. */
  const LEVEL_OF: Record<number, number> = { 5: 1, 4: 2, 3: 3, 2: 3, 1: 4, 0: 5 };
  const level = $derived(kanji ? LEVEL_OF[kanji.jlpt] ?? 5 : 5);

  // Known-kanji set (for Furigana gating in examples).
  let knownKanji = $state<Set<string>>(new Set());
  let bestScore = $state<number | undefined>(undefined);

  onMount(async () => {
    knownKanji = await loadKnownKanji();
    startTick();
  });
  onDestroy(() => stopTick());

  // Best score lookup updates whenever the char changes.
  $effect(() => {
    const c = char;
    getBestScore(c).then((s) => {
      bestScore = s;
    });
  });

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
  const callouts = $derived(kanji?.callouts ?? []);

  const STEPS = [
    { key: 'practice', label: 'Practice' },
    { key: 'examples', label: 'Examples' },
  ] as const;
  type Step = 0 | 1;
  let step = $state<Step>(0);

  $effect(() => {
    void char;
    step = 0;
  });

  /** Bound to PracticeMorph — true while the reference animation is visible,
   *  false once the user starts drawing. Controls whether the hero shows the
   *  plain glyph (visible) or the RevealKanji peek mode (hidden). */
  let showingRef = $state(true);

  /** Deduplicated reading list for the TTS chips. Combines kun (unchanged,
   *  okurigana preserved visually) and on (shown as katakana as stored). */
  const readingChips = $derived.by<string[]>(() => {
    if (!kanji) return [];
    const out: string[] = [];
    const seen = new Set<string>();
    for (const r of kanji.kun) {
      if (r && !seen.has(r)) { seen.add(r); out.push(r); }
    }
    for (const r of kanji.on) {
      if (r && !seen.has(r)) { seen.add(r); out.push(r); }
    }
    return out.slice(0, 6);
  });

  const meaningLine = $derived(
    kanji ? kanji.meanings.slice(0, 3).join(' · ') : '',
  );

  // Encouraging microcopy — current-best-score driven. Stateless per-session
  // so the learner gets the same vibe each time they open the same kanji.
  const encourageLine = $derived.by(() => {
    if (bestScore === undefined) return 'Fresh start. Ready when you are.';
    if (bestScore >= 85) return "Almost there — make it effortless.";
    if (bestScore >= 70) return "You're in range. Stay with each stroke.";
    if (bestScore >= 40) return "Coming along. Keep the rhythm.";
    return "Take your time — every stroke teaches your hand.";
  });

  /** Strip okurigana markers for TTS, keep visual. */
  function cleanForSpeech(r: string): string {
    return r.replace(/[.\-]/g, '').trim();
  }
</script>

<div class="screen">
  {#if !kanji}
    <div class="center">Unknown kanji: {char}</div>
  {:else}
    <!-- ── Back + pills ──────────────────────────────────────── -->
    <header class="topbar">
      <a class="back" href="/" use:link>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back
      </a>
      <div class="pills">
        <span class="pill pill-accent"><Petal size={10} /> L{level}</span>
        <span class="pill pill-muted">{kanji.strokes} strokes</span>
      </div>
    </header>

    <!-- ── Hero kanji card ───────────────────────────────────── -->
    <section class="hero">
      <PetalField count={8} />

      <div class="hero-row">
        <div class="glyph-tile">
          {#if showingRef || step === 1}
            <div class="glyph jp-serif">{kanji.char}</div>
          {:else}
            {#key char}
              <RevealKanji svg={kanji.svg} strokeCount={kanji.strokes} />
            {/key}
          {/if}
          <div class="stroke-count tnum">1 / {kanji.strokes}</div>
        </div>

        <div class="hero-body">
          <div class="kicker">Learn</div>
          <div class="meaning">{meaningLine}</div>
          {#if readingChips.length > 0}
            <div class="reading-chips">
              {#each readingChips as r (r)}
                <button
                  class="r-chip jp-sans"
                  onclick={() => speakJa(cleanForSpeech(r))}
                  disabled={!ttsSupported()}
                >
                  <svg class="r-play" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
                  {r}
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      <div class="encourage">
        <span class="encourage-icon" aria-hidden="true"><Blossom size={18} /></span>
        <span>{encourageLine}</span>
      </div>
    </section>

    <!-- ── Stepper ──────────────────────────────────────────── -->
    <nav class="stepper" aria-label="Lesson steps">
      {#each STEPS as s, i}
        <button
          class="step"
          class:active={step === i}
          onclick={() => (step = i as Step)}
        >
          <span class="step-num">{i + 1}</span>
          <span>{s.label}</span>
        </button>
      {/each}
    </nav>

    <!-- ── Practice / Examples body ─────────────────────────── -->
    {#if step === 0}
      <section class="practice-card">
        <div class="practice-head">
          <div class="practice-title">Draw the kanji</div>
        </div>
        {#key char + 'morph'}
          <PracticeMorph {kanji} {callouts} {knownKanji} onRefChange={(v) => (showingRef = v)} />
        {/key}
      </section>
    {:else}
      <section class="examples-card">
        <div class="card-kicker">Examples · tap to play</div>
        {#if tooAdvanced && examples.length > 0}
          <p class="advanced-hint">
            These sentences include kanji you haven't mastered yet. Keep practicing and they'll clear up.
          </p>
        {/if}
        {#if examples.length === 0}
          <p class="muted">No example sentences for this kanji yet.</p>
        {:else}
          <ul class="examples-list">
            {#each examples as ex, i (exampleJp(ex))}
              <li class="example" class:dashed={i < examples.length - 1}>
                <div class="ex-row">
                  <div
                    class="ex-jp"
                    role="button"
                    tabindex="0"
                    aria-label="Tap to hear the sentence"
                    onclick={() => speakJa(exampleJp(ex))}
                    onkeydown={(e) => e.key === 'Enter' && speakJa(exampleJp(ex))}
                  >
                    <Furigana segments={ex.segs} knownKanji={knownKanji} currentKanji={char} />
                  </div>
                  <button
                    class="ex-speak"
                    onclick={(e) => { e.stopPropagation(); speakJa(exampleJp(ex)); }}
                    aria-label="Speak sentence"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                  </button>
                </div>
                <div class="ex-en">{ex.en}</div>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}

    {#if step === 1 && words.length > 1}
      <section class="words-card">
        <div class="card-kicker">Words using {kanji.char}</div>
        <div class="word-grid">
          {#each words.slice(0, 12) as w (w.id)}
            <a
              class="word-card"
              href={`/vocab/${encodeURIComponent(w.id)}`}
              use:link
              onclick={() => sessionStorage.setItem('vocab-from-learn', char)}
            >
              <div class="w-jp jp-serif">{w.jp}</div>
              <div class="w-reading jp-sans">{w.reading}</div>
              <div class="w-en">{w.meanings[0] ?? ''}</div>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- ── Footer nav ───────────────────────────────────────── -->
    <div class="foot">
      <button
        class="foot-btn ghost"
        onclick={() => (step = Math.max(0, step - 1) as Step)}
        disabled={step === 0}
      >← Back</button>
      <a class="foot-btn" href="/" use:link>Home</a>
      {#if step === 0}
        <button class="foot-btn primary" onclick={() => (step = 1)}>Next →</button>
      {:else if words.length}
        <a class="foot-btn primary" href={`/vocab/${encodeURIComponent(words[0].id)}`} use:link>Vocab →</a>
      {:else}
        <a class="foot-btn primary" href="/" use:link>Done</a>
      {/if}
    </div>
  {/if}
</div>

<style>
  .screen {
    max-width: 820px;
    margin: 0 auto;
    padding: 16px 16px 40px;
  }
  .center { padding: 2rem; text-align: center; color: var(--muted); }

  /* ── Topbar ─────────────────────────────────────────────── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .back {
    padding: 8px 12px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink-2);
    font-size: 13px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .pills { display: flex; gap: 6px; }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .pill-accent { background: var(--accent-soft); color: var(--accent); }
  .pill-muted { background: var(--surface-2); color: var(--ink-2); }

  /* ── Hero kanji card ────────────────────────────────────── */
  .hero {
    position: relative;
    border-radius: 26px;
    background: var(--hero-grad);
    padding: 22px;
    margin-bottom: 12px;
    border: 1px solid var(--border);
    box-shadow: var(--shadow-md);
    overflow: hidden;
  }
  .hero-row {
    position: relative;
    z-index: 1;
    display: flex;
    gap: 20px;
    align-items: center;
  }
  .glyph-tile {
    width: 180px;
    height: 180px;
    background: var(--surface);
    border-radius: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, 0.4),
      var(--shadow-sm);
    flex-shrink: 0;
    position: relative;
  }
  .glyph {
    font-size: 120px;
    color: var(--ink);
    line-height: 1;
  }
  .stroke-count {
    position: absolute;
    bottom: 8px;
    right: 10px;
    font-size: 10px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .hero-body { flex: 1; min-width: 0; }
  .kicker {
    font-size: 11px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .meaning {
    font-size: 20px;
    font-weight: 800;
    line-height: 1.2;
    color: var(--ink);
    margin-bottom: 10px;
  }
  .reading-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .r-chip {
    padding: 6px 12px;
    border-radius: 999px;
    background: var(--surface);
    border: 1px solid var(--border);
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .r-play { color: var(--accent); }

  .encourage {
    position: relative;
    z-index: 1;
    margin-top: 12px;
    padding: 10px 14px;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid var(--border);
    border-radius: 14px;
    font-size: 13px;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 8px;
    backdrop-filter: blur(8px);
  }
  :global([data-theme='neon']) .encourage {
    background: rgba(0, 0, 0, 0.35);
    color: var(--ink);
  }
  .encourage-icon { color: var(--accent); display: inline-flex; }

  /* ── Stepper ────────────────────────────────────────────── */
  .stepper {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
  .step {
    flex: 1;
    padding: 10px 14px;
    border-radius: 14px;
    background: var(--surface);
    color: var(--ink-2);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-weight: 700;
    font-size: 13px;
  }
  .step.active {
    background: var(--ink);
    color: var(--surface);
    border-color: var(--ink);
  }
  .step-num {
    width: 22px;
    height: 22px;
    border-radius: 999px;
    background: var(--surface-2);
    color: var(--muted);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 800;
  }
  .step.active .step-num {
    background: var(--accent);
    color: #fff;
  }

  /* ── Practice card ──────────────────────────────────────── */
  .practice-card {
    border-radius: 22px;
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 18px;
    box-shadow: var(--shadow-sm);
    margin-bottom: 12px;
  }
  .practice-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .practice-title {
    font-size: 13px;
    font-weight: 800;
    color: var(--ink);
  }

  /* ── Examples card ──────────────────────────────────────── */
  .examples-card,
  .words-card {
    border-radius: 22px;
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 16px 18px;
    box-shadow: var(--shadow-sm);
    margin-bottom: 12px;
  }
  .card-kicker {
    font-size: 11px;
    font-weight: 800;
    color: var(--muted);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 10px;
  }
  .advanced-hint {
    background: color-mix(in oklab, var(--accent-2) 18%, var(--surface));
    border: 1px solid color-mix(in oklab, var(--accent-2) 40%, transparent);
    color: var(--ink);
    padding: 10px 12px;
    border-radius: 12px;
    font-size: 12.5px;
    margin: 0 0 10px;
  }
  .examples-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .example { padding: 10px 0; }
  .example.dashed { border-bottom: 1px dashed var(--border); }
  .ex-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }
  .ex-jp {
    flex: 1;
    min-width: 0;
    color: var(--ink);
    font-size: 17px;
    line-height: 1.4;
    cursor: pointer;
  }
  .ex-jp:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 4px;
    border-radius: 4px;
  }
  .ex-speak {
    flex-shrink: 0;
    padding: 6px 8px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--ink-2);
    line-height: 0;
  }
  .ex-speak:hover { color: var(--accent); border-color: var(--accent); }
  .ex-en {
    color: var(--ink-2);
    font-size: 12.5px;
    margin-top: 4px;
    line-height: 1.4;
  }

  /* ── Words list ─────────────────────────────────────────── */
  .word-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
  }
  .word-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 10px 12px;
    color: var(--ink);
  }
  .w-jp { font-size: 18px; line-height: 1.2; }
  .w-reading { color: var(--ink-2); font-size: 12px; margin-top: 2px; }
  .w-en { color: var(--ink-2); font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* ── Footer nav ─────────────────────────────────────────── */
  .foot {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }
  .foot-btn {
    flex: 1;
    padding: 12px;
    border-radius: 14px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink);
    font-weight: 700;
    font-size: 14px;
    text-align: center;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .foot-btn.ghost { color: var(--ink-2); }
  .foot-btn.primary {
    background: var(--gradient-brand);
    color: #fff;
    /* Keep the 1px border for height-parity with ghost siblings, but clip
       the gradient to the padding box so anti-aliased border pixels don't
       bleed a hue fringe against dark backgrounds on Neon. */
    border-color: transparent;
    background-clip: padding-box;
    box-shadow: var(--shadow-sm);
  }
  :global([data-theme='washi']) .foot-btn.primary { color: #2B231A; }
  .foot-btn:disabled { opacity: 0.4; }

  .muted { color: var(--muted); }

  @media (max-width: 520px) {
    .hero-row { flex-direction: column; align-items: stretch; gap: 12px; }
    .glyph-tile { width: 100%; height: 170px; }
  }
</style>
