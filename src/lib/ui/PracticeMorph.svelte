<script lang="ts">
  import { onMount } from 'svelte';
  import type { Callout, Kanji } from '../data/types';
  import { speakJa, ttsSupported } from '../speech/tts';
  import { resample, type Point } from '../stroke/compare';
  import { appendAttempt, getBestScore, getRecentAttempts, putBestScoreIfBetter } from '../data/db';
  import { textUsesOnlyKnown } from '../data/known';

  interface Props {
    kanji: Kanji;
    callouts?: Callout[];
    knownKanji?: ReadonlySet<string>;
  }
  const { kanji, callouts = [], knownKanji }: Props = $props();

  // Callouts whose example sentences use only kanji the learner has mastered
  // (plus the current kanji itself). If filtering removes everything, fall
  // back to the full list so first-session users still hear something.
  const filteredCallouts = $derived.by<Callout[]>(() => {
    if (!knownKanji || knownKanji.size === 0) return callouts;
    const kept = callouts.filter((c) => textUsesOnlyKnown(c.exJp, knownKanji, kanji.char));
    return kept.length > 0 ? kept : callouts;
  });

  // KanjiVG viewBox + how many points to resample per stroke during morph.
  const VB = 109;
  const RESAMPLE_N = 64;
  const FULL_MORPH_MS = 1500;
  const QUICK_MORPH_MS = 350;
  const HISTORY_MAX = 6;

  let host: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;

  // ── reactive state ─────────────────────────────────────────────────
  // refPaths must be $state so $derived(requiredCount) recomputes after onMount.
  let refPaths = $state<SVGPathElement[]>([]);
  let userStrokes = $state<Point[][]>([]);
  let drawing = $state(false);
  let currentPoints: Point[] = [];
  let morphing = $state(false);
  let morphed = $state(false);
  let seenFullMorph = $state(false);
  let currentCallout = $state<Callout | null>(null);
  let score = $state<number | null>(null);
  let history = $state<number[]>([]);
  let best = $state<number | null>(null);

  const requiredCount = $derived(refPaths.length);
  const drawnCount = $derived(userStrokes.length);
  const canMorph = $derived(drawnCount >= 1 && !morphing);

  const delta = $derived.by(() => {
    if (history.length < 2) return null;
    return history[history.length - 1] - history[history.length - 2];
  });

  // Reset everything whenever the parent swaps to a new kanji, and hydrate
  // the persisted best + attempt history so the score strip isn't empty on
  // first load / reload / navigation.
  $effect(() => {
    void kanji.char;
    const char = kanji.char;
    history = [];
    seenFullMorph = false;
    currentCallout = null;
    score = null;
    best = null;
    getBestScore(char).then((b) => {
      if (b !== undefined && char === kanji.char) best = b;
    });
    getRecentAttempts(char, HISTORY_MAX).then((attempts) => {
      if (char !== kanji.char) return;
      history = attempts.map((a) => a.score);
    });
    if (ctx) reset(/* keepHistory */ false);
  });

  // ── canvas drawing ─────────────────────────────────────────────────
  function clearCanvas() {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function drawStroke(pts: Point[], color: string) {
    if (!ctx || pts.length < 2) return;
    const sx = canvas.width / VB;
    const sy = canvas.height / VB;
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(4, canvas.width / 26);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(pts[0].x * sx, pts[0].y * sy);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x * sx, pts[i].y * sy);
    ctx.stroke();
  }

  function redraw() {
    clearCanvas();
    for (const s of userStrokes) drawStroke(s, '#ff7a59');
    if (drawing && currentPoints.length) drawStroke(currentPoints, '#ff7a59');
  }

  function canvasPoint(e: PointerEvent): Point {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * VB,
      y: ((e.clientY - rect.top) / rect.height) * VB,
    };
  }

  function onDown(e: PointerEvent) {
    if (morphing) return;
    drawing = true;
    // Wrap setPointerCapture: it can throw on non-trusted events (e.g. synthetic
    // pointer events from automation harnesses). If it fails we still capture
    // points via the move handler; we just miss out on implicit capture.
    try { canvas.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    currentPoints = [canvasPoint(e)];
  }

  function onMove(e: PointerEvent) {
    if (!drawing) return;
    currentPoints.push(canvasPoint(e));
    redraw();
  }

  function onUp() {
    if (!drawing) return;
    drawing = false;
    if (currentPoints.length >= 2) {
      userStrokes = [...userStrokes, currentPoints];
    }
    currentPoints = [];
    redraw();
  }

  // ── scoring ────────────────────────────────────────────────────────
  /** Score the current user strokes against the reference paths. Returns
   * 0-100 where 100 = perfect. Penalizes missing strokes, extra strokes,
   * and per-stroke mean distance in VB space. Defensive against NaN-producing
   * inputs (sampling failures, zero-length paths, single-point strokes). */
  function computeScore(): number {
    if (!refPaths.length) return 0;

    const refSamples = refPaths.map((p) => sampleRefPath(p, RESAMPLE_N));
    const N = Math.max(userStrokes.length, refSamples.length);
    if (N === 0) return 0;
    let distSum = 0;

    for (let i = 0; i < N; i++) {
      const ref = refSamples[i];
      const usr = userStrokes[i];
      if (!ref) {
        // User drew an extra stroke beyond what was needed.
        distSum += 40;
        continue;
      }
      if (!usr || usr.length < 2) {
        // User didn't draw this stroke at all.
        distSum += 45;
        continue;
      }
      const us = resample(usr, RESAMPLE_N);
      if (us.length < RESAMPLE_N) {
        // resample() refuses if the input has < 2 points — treat like missing.
        distSum += 45;
        continue;
      }
      let local = 0;
      let counted = 0;
      for (let j = 0; j < RESAMPLE_N; j++) {
        const dx = us[j].x - ref[j].x;
        const dy = us[j].y - ref[j].y;
        const d = Math.hypot(dx, dy);
        if (Number.isFinite(d)) {
          local += d;
          counted += 1;
        }
      }
      distSum += counted > 0 ? local / counted : 45;
    }

    const avg = distSum / N;
    if (!Number.isFinite(avg)) return 0;
    // Linear mapping: avg=0 → 100, avg=40 → 0.
    const raw = 100 - avg * 2.5;
    return Math.max(0, Math.min(100, Math.round(raw)));
  }

  // ── morph animation ────────────────────────────────────────────────
  function sampleRefPath(p: SVGPathElement, n: number): Point[] {
    const total = p.getTotalLength();
    const out: Point[] = [];
    for (let i = 0; i < n; i++) {
      const pt = p.getPointAtLength((i / (n - 1)) * total);
      out.push({ x: pt.x, y: pt.y });
    }
    return out;
  }

  function easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function pickRandomCallout(): Callout | null {
    const pool = filteredCallouts;
    if (!pool.length) return null;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function speakCallout(c: Callout) {
    if (!ttsSupported()) return;
    speakJa(c.wordReading);
    window.setTimeout(() => speakJa(c.exJp), 1150);
  }

  async function runMorph(full: boolean) {
    if (!ctx || morphing || !canMorph) return;
    morphing = true;

    // Compute and record score first so it's immediately visible when animation ends.
    const s = computeScore();
    score = s;
    history = [...history, s].slice(-HISTORY_MAX);
    // Persist best and a full attempt record. Both are fire-and-forget; a
    // storage hiccup should never block the animation.
    putBestScoreIfBetter(kanji.char, s).then((nb) => {
      best = nb;
    });
    appendAttempt({
      char: kanji.char,
      score: s,
      strokeCount: userStrokes.length,
      requiredStrokes: refPaths.length,
      ts: Date.now(),
    }).catch(() => {});

    // Pick a random callout from the filtered set and (optionally) speak it.
    const callout = pickRandomCallout();
    currentCallout = callout;
    if (full && callout) speakCallout(callout);

    morphed = true;
    if (full) seenFullMorph = true;

    const userResampled = userStrokes.map((s2) => resample(s2, RESAMPLE_N));
    const refResampled = refPaths.map((p) => sampleRefPath(p, RESAMPLE_N));
    const N = Math.max(userResampled.length, refResampled.length);
    const pairs: [Point[], Point[]][] = [];
    for (let i = 0; i < N; i++) {
      const r = refResampled[i] ?? refResampled[refResampled.length - 1];
      const fallback = Array.from({ length: RESAMPLE_N }, () => ({ ...r[0] }));
      const u = userResampled[i] ?? fallback;
      pairs.push([u, r]);
    }

    const duration = full ? FULL_MORPH_MS : QUICK_MORPH_MS;
    const sx = canvas.width / VB;
    const sy = canvas.height / VB;
    const start = performance.now();

    await new Promise<void>((resolve) => {
      function frame(now: number) {
        if (!ctx) return;
        const t = Math.min(1, (now - start) / duration);
        const e = easeInOutCubic(t);

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.lineWidth = Math.max(4, canvas.width / 26);

        for (const [u, r] of pairs) {
          const lerp = (a: number, b: number) => a + (b - a) * e;
          const cr = Math.round(lerp(255, 232));
          const cg = Math.round(lerp(122, 232));
          const cb = Math.round(lerp(89, 234));
          ctx.strokeStyle = `rgb(${cr}, ${cg}, ${cb})`;

          ctx.beginPath();
          for (let i = 0; i < u.length; i++) {
            const x = u[i].x + (r[i].x - u[i].x) * e;
            const y = u[i].y + (r[i].y - u[i].y) * e;
            if (i === 0) ctx.moveTo(x * sx, y * sy);
            else ctx.lineTo(x * sx, y * sy);
          }
          ctx.stroke();
        }

        if (t < 1) requestAnimationFrame(frame);
        else {
          morphing = false;
          resolve();
        }
      }
      requestAnimationFrame(frame);
    });
  }

  async function onPrimary() {
    // First morph of the session is full (with audio + example); subsequent
    // morphs are quick so the user can iterate without sitting through it.
    await runMorph(/* full */ !seenFullMorph);
  }

  async function onReplayFull() {
    if (morphing || userStrokes.length === 0) return;
    // Force the full animation + speech again.
    await runMorph(true);
  }

  function reset(keepHistory = true) {
    userStrokes = [];
    currentPoints = [];
    drawing = false;
    morphing = false;
    morphed = false;
    score = null;
    if (!keepHistory) history = [];
    redraw();
  }

  function tapCallout() {
    if (currentCallout) speakCallout(currentCallout);
  }

  function tone(v: number): 'gold' | 'mid' | 'bad' {
    if (v >= 85) return 'gold';
    if (v >= 60) return 'mid';
    return 'bad';
  }

  // ── mount: parse the kanji SVG so we can sample reference paths ─────
  onMount(() => {
    host.innerHTML = kanji.svg;
    const svgEl = host.querySelector('svg');
    if (svgEl) {
      svgEl.setAttribute('viewBox', `0 0 ${VB} ${VB}`);
      svgEl.setAttribute('width', '100%');
      svgEl.setAttribute('height', '100%');
      svgEl.style.position = 'absolute';
      svgEl.style.inset = '0';
      svgEl.style.opacity = '0';
      svgEl.style.pointerEvents = 'none';
      refPaths = Array.from(svgEl.querySelectorAll('path'));
    }

    ctx = canvas.getContext('2d');
    const size = Math.min(host.clientWidth, 420);
    canvas.width = size;
    canvas.height = size;
    host.style.width = host.style.height = `${size}px`;
  });
</script>

<div class="hint-row">
  <span class="big">
    Draw <b>{requiredCount}</b> strokes
  </span>
  <span class="counter">({drawnCount} / {requiredCount})</span>
  {#if best !== null}
    <span class="best-inline">· best <b>{best}</b></span>
  {/if}
</div>

<div class="wrap">
  <div class="stage" bind:this={host}></div>
  <canvas
    bind:this={canvas}
    onpointerdown={onDown}
    onpointermove={onMove}
    onpointerup={onUp}
    onpointercancel={onUp}
  ></canvas>
</div>

<!-- Score + history strip. Visible whenever there's *any* signal to show:
     a brand-new score this session, or a history strip hydrated from IDB. -->
{#if score !== null || history.length > 0}
  <div class="score-row">
    {#if score !== null}
      <div class="score-big {tone(score)}">
        <span class="num">{score}</span>
        <span class="lbl">/100</span>
      </div>
    {:else}
      <div class="score-big muted-big">
        <span class="num">–</span>
        <span class="lbl">draw & morph</span>
      </div>
    {/if}
    <div class="score-side">
      <div class="history">
        {#each history as h, i (i)}
          <span class="pill {tone(h)}" class:latest={i === history.length - 1 && score !== null}>{h}</span>
        {/each}
      </div>
      {#if delta !== null && score !== null}
        <div class="delta {delta > 0 ? 'up' : delta < 0 ? 'down' : ''}">
          {delta > 0 ? '▲' : delta < 0 ? '▼' : '•'} {delta > 0 ? '+' : ''}{delta} from last
        </div>
      {:else if score === null && history.length > 0}
        <div class="delta muted">Past attempts from memory — draw to beat your streak.</div>
      {:else}
        <div class="delta muted">First attempt — keep going.</div>
      {/if}
    </div>
  </div>
{/if}

<!-- Random callout that appeared during the morph -->
{#if currentCallout}
  <button class="callout-card" onclick={tapCallout} aria-label="Replay callout audio">
    <div class="tag-label">Example <span class="hint-tap">tap to replay 🔊</span></div>
    <div class="tag-jp">
      {currentCallout.wordJp}
      <span class="tag-reading">{currentCallout.wordReading}</span>
    </div>
    <div class="tag-en">{currentCallout.wordMeaning}</div>
    <div class="tag-sentence">{currentCallout.exJp}</div>
    <div class="tag-sentence-en">{currentCallout.exEn}</div>
  </button>
{/if}

<div class="row">
  <button onclick={() => reset(true)} disabled={drawnCount === 0 && !morphed}>
    ↺ Restart
  </button>
  {#if !morphed}
    <button class="primary" onclick={onPrimary} disabled={!canMorph}>
      ✨ Morph into kanji
    </button>
  {:else}
    <button class="primary" onclick={() => reset(true)}>Draw again</button>
    <button class="tertiary" onclick={onReplayFull} disabled={morphing}>↻ Full replay</button>
  {/if}
</div>

<style>
  .hint-row {
    text-align: center;
    margin-bottom: 0.75rem;
    color: var(--fg-dim);
    font-size: 0.95rem;
  }
  .big {
    color: var(--fg);
    font-size: 1.05rem;
  }
  .counter {
    color: var(--fg-dim);
    margin-left: 0.5rem;
    font-variant-numeric: tabular-nums;
  }
  .best-inline {
    color: var(--fg-dim);
    margin-left: 0.5rem;
    font-variant-numeric: tabular-nums;
  }
  .best-inline b {
    color: var(--accent);
  }

  .wrap {
    position: relative;
    width: min(80vw, 420px);
    aspect-ratio: 1 / 1;
    margin: 0 auto;
    background: linear-gradient(135deg, #2a2a32, #20202a);
    border-radius: 20px;
    border: 1px solid var(--border);
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.04);
    overflow: hidden;
  }
  .wrap::before {
    content: '';
    position: absolute;
    inset: 0;
    background:
      linear-gradient(to right, transparent calc(50% - 1px), rgba(255, 255, 255, 0.05) calc(50% - 1px), rgba(255, 255, 255, 0.05) calc(50% + 1px), transparent calc(50% + 1px)),
      linear-gradient(to bottom, transparent calc(50% - 1px), rgba(255, 255, 255, 0.05) calc(50% - 1px), rgba(255, 255, 255, 0.05) calc(50% + 1px), transparent calc(50% + 1px));
    pointer-events: none;
  }
  .stage {
    position: absolute;
    inset: 0;
  }
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    touch-action: none;
  }

  /* ── score + history ───────────────────────────────────────────── */
  .score-row {
    margin: 1rem auto 0;
    max-width: 420px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 1rem;
    align-items: center;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0.85rem 1rem;
    animation: fade-in 0.25s ease-out;
  }
  .score-big {
    display: flex;
    align-items: baseline;
    gap: 0.15rem;
    font-variant-numeric: tabular-nums;
    padding: 0.25rem 0.8rem;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.04);
  }
  .score-big .num {
    font-size: 2.1rem;
    font-weight: 800;
    line-height: 1;
  }
  .score-big .lbl {
    font-size: 0.85rem;
    color: var(--fg-dim);
  }
  .score-big.gold .num {
    color: #ffd24a;
    text-shadow: 0 0 18px rgba(255, 210, 74, 0.45);
  }
  .score-big.mid  .num { color: var(--accent); }
  .score-big.bad  .num { color: var(--err); }
  .score-big.muted-big .num { color: var(--fg-dim); }
  .score-big.muted-big .lbl { font-size: 0.7rem; }

  .score-side { display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; }
  .history {
    display: flex;
    gap: 0.3rem;
    flex-wrap: wrap;
  }
  .pill {
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
    color: var(--fg-dim);
  }
  .pill.good { color: var(--ok); border-color: rgba(94, 202, 124, 0.35); }
  .pill.mid  { color: var(--accent); border-color: rgba(255, 122, 89, 0.35); }
  .pill.bad  { color: var(--err); border-color: rgba(255, 107, 107, 0.35); }
  .pill.latest { box-shadow: 0 0 0 2px rgba(255, 122, 89, 0.25); font-weight: 700; }

  .delta {
    font-size: 0.75rem;
    color: var(--fg-dim);
    font-variant-numeric: tabular-nums;
  }
  .delta.up { color: var(--ok); }
  .delta.down { color: var(--err); }
  .delta.muted { font-style: italic; }

  /* ── callout card ──────────────────────────────────────────────── */
  .callout-card {
    display: block;
    width: 100%;
    max-width: 420px;
    margin: 0.75rem auto 0;
    background: linear-gradient(135deg, rgba(124, 92, 255, 0.16), rgba(124, 92, 255, 0.04));
    border: 1px solid rgba(124, 92, 255, 0.35);
    border-radius: 14px;
    padding: 0.85rem 1rem;
    text-align: center;
    color: var(--fg);
    animation: fade-in 0.4s ease-out;
    cursor: pointer;
  }
  .callout-card:hover { border-color: rgba(124, 92, 255, 0.55); }
  .tag-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    font-weight: 600;
    margin-bottom: 0.35rem;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .hint-tap {
    text-transform: none;
    letter-spacing: 0;
    font-weight: 400;
    opacity: 0.8;
  }
  .tag-jp {
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.5rem;
    line-height: 1.1;
  }
  .tag-reading {
    font-size: 0.9rem;
    color: var(--fg-dim);
    margin-left: 0.4rem;
    font-family: 'Hiragino Sans', system-ui;
  }
  .tag-en {
    color: var(--fg-dim);
    font-size: 0.85rem;
    margin: 0.25rem 0 0.6rem;
  }
  .tag-sentence {
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.1rem;
    color: var(--fg);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding-top: 0.6rem;
    margin-top: 0.25rem;
  }
  .tag-sentence-en {
    color: var(--fg-dim);
    font-size: 0.85rem;
    margin-top: 0.3rem;
  }

  @keyframes fade-in {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .row {
    display: flex;
    gap: 0.5rem;
    justify-content: center;
    margin-top: 1rem;
    flex-wrap: wrap;
  }
  .row button {
    min-width: 8rem;
    padding: 0.8rem 1rem;
    font-size: 0.95rem;
  }
  .row button.tertiary {
    background: transparent;
    border-color: rgba(255, 255, 255, 0.12);
    color: var(--fg-dim);
  }
</style>
