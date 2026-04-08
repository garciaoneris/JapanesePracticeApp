<script lang="ts">
  import { onMount } from 'svelte';
  import type { Kanji, Word } from '../data/types';
  import { speakJa, ttsSupported } from '../speech/tts';
  import { resample, type Point } from '../stroke/compare';

  interface Props {
    kanji: Kanji;
    exampleWord?: Word | null;
  }
  const { kanji, exampleWord = null }: Props = $props();

  // KanjiVG viewBox + how many points to interpolate per stroke during morph.
  const VB = 109;
  const RESAMPLE_N = 64;
  const MORPH_MS = 1500;

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

  const requiredCount = $derived(refPaths.length);
  const drawnCount = $derived(userStrokes.length);
  const canMorph = $derived(drawnCount >= 1 && !morphing && !morphed);

  // Reset whenever the parent swaps to a new kanji.
  $effect(() => {
    void kanji.char;
    if (ctx) reset();
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
    if (morphing || morphed) return;
    drawing = true;
    canvas.setPointerCapture(e.pointerId);
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

  async function morph() {
    if (!canMorph || !ctx) return;
    morphing = true;
    morphed = true;

    const userResampled = userStrokes.map((s) => resample(s, RESAMPLE_N));
    const refResampled = refPaths.map((p) => sampleRefPath(p, RESAMPLE_N));

    // Pair user strokes with reference strokes by index. If counts differ, pad
    // missing user strokes with the matching reference stroke's start point so
    // those strokes appear to "grow into existence" during the morph.
    const N = Math.max(userResampled.length, refResampled.length);
    const pairs: [Point[], Point[]][] = [];
    for (let i = 0; i < N; i++) {
      const r = refResampled[i] ?? refResampled[refResampled.length - 1];
      const fallback = Array.from({ length: RESAMPLE_N }, () => ({ ...r[0] }));
      const u = userResampled[i] ?? fallback;
      pairs.push([u, r]);
    }

    // Speak the kanji reading immediately, then the example word a beat later.
    if (ttsSupported()) {
      const reading = kanji.kun[0]?.replace(/[.\-]/g, '') ?? kanji.on[0] ?? kanji.char;
      speakJa(reading);
      if (exampleWord) {
        window.setTimeout(() => speakJa(exampleWord.jp), 1100);
      }
    }

    // Animate.
    const sx = canvas.width / VB;
    const sy = canvas.height / VB;
    const start = performance.now();

    await new Promise<void>((resolve) => {
      function frame(now: number) {
        if (!ctx) return;
        const t = Math.min(1, (now - start) / MORPH_MS);
        const e = easeInOutCubic(t);

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.lineWidth = Math.max(4, canvas.width / 26);

        for (const [u, r] of pairs) {
          // Color shifts from accent orange to the "settled" off-white.
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

  function reset() {
    userStrokes = [];
    currentPoints = [];
    drawing = false;
    morphing = false;
    morphed = false;
    redraw();
  }

  // ── mount: parse the kanji SVG so we can sample reference paths ─────
  onMount(() => {
    // Mount the SVG hidden inside `host`. We need it in the live DOM so
    // SVGPathElement.getPointAtLength()/getTotalLength() work; opacity:0 keeps
    // it invisible without removing it from the layout tree.
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
  {#if !morphed}
    <span class="big">Draw <b>{requiredCount}</b> strokes</span>
    <span class="counter">({drawnCount} / {requiredCount})</span>
  {:else}
    <span class="big done">✓ {kanji.meanings.slice(0, 2).join(', ')}</span>
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

{#if morphed && exampleWord}
  <div class="example-tag">
    <div class="tag-label">Example</div>
    <div class="tag-jp">{exampleWord.jp} <span class="tag-reading">{exampleWord.reading}</span></div>
    <div class="tag-en">{exampleWord.meanings.slice(0, 2).join('; ')}</div>
  </div>
{/if}

<div class="row">
  {#if !morphed}
    <button class="primary" onclick={morph} disabled={!canMorph}>
      ✨ Morph into kanji
    </button>
  {:else}
    <button onclick={reset}>↺ Try again</button>
    <button class="primary" onclick={morph} disabled={morphing}>↻ Replay morph</button>
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
  .big.done {
    color: var(--ok);
    font-weight: 600;
  }
  .counter {
    color: var(--fg-dim);
    margin-left: 0.5rem;
    font-variant-numeric: tabular-nums;
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
    /* faint genkō-yōshi style cross hairs */
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

  .example-tag {
    margin: 1rem auto 0;
    max-width: 420px;
    background: linear-gradient(135deg, rgba(94, 202, 124, 0.14), rgba(94, 202, 124, 0.04));
    border: 1px solid rgba(94, 202, 124, 0.35);
    border-radius: 14px;
    padding: 0.85rem 1rem;
    text-align: center;
    animation: fade-in 0.4s ease-out;
  }
  .tag-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    font-weight: 600;
    margin-bottom: 0.25rem;
  }
  .tag-jp {
    font-family: 'Hiragino Mincho ProN', serif;
    font-size: 1.4rem;
    color: var(--fg);
  }
  .tag-reading {
    font-size: 0.85rem;
    color: var(--fg-dim);
    margin-left: 0.4rem;
    font-family: 'Hiragino Sans', system-ui;
  }
  .tag-en {
    color: var(--fg);
    font-size: 0.95rem;
    margin-top: 0.25rem;
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
  }
  .row button {
    min-width: 9rem;
    padding: 0.85rem 1.2rem;
    font-size: 1rem;
  }
</style>
