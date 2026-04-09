<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { normalizeToBox, pathToPoints, scoreStroke, type Point } from '../stroke/compare';

  type Mode = 'animate' | 'guided' | 'blank';

  interface Props {
    svg: string;
    mode?: Mode;
    onComplete?: () => void;
  }
  const { svg, mode = 'guided', onComplete }: Props = $props();

  // Literal colors mirroring app.css custom props (SVG setAttribute does not resolve var()).
  const C_FG = '#e8e8ea';
  const C_ACCENT = '#ff7a59';
  const C_OK = '#5eca7c';
  const C_BG = '#1b1b1f';

  const VB = 109;

  let host: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let refPaths: SVGPathElement[] = [];
  let refSvg: SVGSVGElement | null = null;

  let currentStroke = $state(0);
  let feedback = $state<string>('');
  let drawing = false;
  let userPoints: Point[] = [];
  let animTimer: number | null = null;
  let animating = $state(false);
  let ready = $state(false);

  // Re-apply whenever the parent switches modes (Listen → Watch → Practice).
  $effect(() => {
    // Touch the prop so the effect re-runs.
    void mode;
    if (ready) reset();
  });

  function clearCanvas() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function showRefForGuided() {
    refPaths.forEach((p, i) => {
      if (i < currentStroke) {
        p.setAttribute('stroke', C_OK);
        p.setAttribute('opacity', '0.55');
        p.removeAttribute('stroke-dasharray');
      } else if (i === currentStroke) {
        p.setAttribute('stroke', C_ACCENT);
        p.setAttribute('opacity', '0.45');
        p.setAttribute('stroke-dasharray', '3 2');
      } else {
        p.setAttribute('opacity', '0');
      }
    });
  }

  function showRefForBlank() {
    refPaths.forEach((p, i) => {
      if (i < currentStroke) {
        p.setAttribute('stroke', C_OK);
        p.setAttribute('opacity', '0.55');
        p.removeAttribute('stroke-dasharray');
      } else {
        p.setAttribute('opacity', '0');
      }
    });
  }

  function clearAnim() {
    if (animTimer != null) {
      window.clearTimeout(animTimer);
      animTimer = null;
    }
  }

  function playAnimation() {
    if (!refPaths.length) return;
    clearAnim();
    animating = true;

    // Reset: hide all paths.
    refPaths.forEach((p) => {
      p.setAttribute('opacity', '0');
      p.removeAttribute('stroke-dasharray');
      p.removeAttribute('stroke-dashoffset');
    });

    // Clear any number markers from a previous play.
    refSvg?.querySelectorAll('.stroke-num').forEach((n) => n.remove());

    let i = 0;
    const PER_STROKE_MS = 700;
    const GAP_MS = 180;

    const playNext = () => {
      if (i >= refPaths.length) {
        animating = false;
        return;
      }
      const p = refPaths[i];
      const len = p.getTotalLength();
      p.setAttribute('opacity', '1');
      p.setAttribute('stroke', C_ACCENT);
      p.setAttribute('stroke-dasharray', `${len}`);
      p.setAttribute('stroke-dashoffset', `${len}`);
      // Force layout flush so the transition runs.
      void p.getBoundingClientRect();
      p.style.transition = `stroke-dashoffset ${PER_STROKE_MS}ms ease-out`;
      p.setAttribute('stroke-dashoffset', '0');

      // After this stroke, fade it to the "done" colour and add a numbered marker at its start.
      animTimer = window.setTimeout(() => {
        p.style.transition = '';
        p.setAttribute('stroke', C_FG);
        p.setAttribute('opacity', '0.85');
        const start = p.getPointAtLength(0);
        addStrokeNumber(start.x, start.y, i + 1);
        i += 1;
        animTimer = window.setTimeout(playNext, GAP_MS);
      }, PER_STROKE_MS);
    };

    playNext();
  }

  function addStrokeNumber(x: number, y: number, n: number) {
    if (!refSvg) return;
    const NS = 'http://www.w3.org/2000/svg';
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'stroke-num');
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('cx', String(x));
    c.setAttribute('cy', String(y));
    c.setAttribute('r', '8');
    c.setAttribute('fill', C_ACCENT);
    c.setAttribute('stroke', C_BG);
    c.setAttribute('stroke-width', '1.5');
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', String(x));
    t.setAttribute('y', String(y + 3.2));
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('font-size', '9');
    t.setAttribute('font-weight', '700');
    t.setAttribute('fill', '#fff');
    t.setAttribute('font-family', 'system-ui, sans-serif');
    t.textContent = String(n);
    g.appendChild(c);
    g.appendChild(t);
    refSvg.appendChild(g);
  }

  function reset() {
    clearAnim();
    animating = false;
    currentStroke = 0;
    feedback = '';
    userPoints = [];
    clearCanvas();
    refSvg?.querySelectorAll('.stroke-num').forEach((n) => n.remove());
    applyMode();
  }

  function applyMode() {
    if (!refPaths.length) return;
    if (mode === 'animate') {
      playAnimation();
    } else if (mode === 'guided') {
      showRefForGuided();
    } else {
      showRefForBlank();
    }
  }

  function canvasPoint(e: PointerEvent): Point {
    const rect = canvas.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * VB, y: ((e.clientY - rect.top) / rect.height) * VB };
  }

  function onDown(e: PointerEvent) {
    if (mode === 'animate') return;
    if (currentStroke >= refPaths.length) return;
    drawing = true;
    canvas.setPointerCapture(e.pointerId);
    userPoints = [canvasPoint(e)];
    feedback = '';
  }

  function onMove(e: PointerEvent) {
    if (!drawing || !ctx) return;
    const p = canvasPoint(e);
    const prev = userPoints[userPoints.length - 1];
    userPoints.push(p);
    const sx = canvas.width / VB;
    const sy = canvas.height / VB;
    ctx.strokeStyle = '#ff7a59';
    ctx.lineWidth = Math.max(4, canvas.width / 28);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(prev.x * sx, prev.y * sy);
    ctx.lineTo(p.x * sx, p.y * sy);
    ctx.stroke();
  }

  function onUp() {
    if (!drawing) return;
    drawing = false;
    if (userPoints.length < 2) return;
    const ref = refPaths[currentStroke];
    if (!ref) return;
    const refPoints = pathToPoints(ref, 32);
    const refNorm = normalizeToBox(refPoints, VB, VB);
    const userNorm = normalizeToBox(userPoints, VB, VB);
    const score = scoreStroke(userNorm, refNorm);
    if (score.pass) {
      feedback = `✓ stroke ${currentStroke + 1}`;
      currentStroke += 1;
      if (mode === 'guided') showRefForGuided();
      else showRefForBlank();
      if (currentStroke >= refPaths.length) {
        feedback = '✓ complete!';
        onComplete?.();
      }
    } else {
      feedback = `retry — try going in the right direction`;
    }
  }

  onMount(() => {
    host.innerHTML = svg;
    refSvg = host.querySelector('svg');
    if (!refSvg) return;
    refSvg.setAttribute('width', '100%');
    refSvg.setAttribute('height', '100%');
    refSvg.setAttribute('viewBox', `0 0 ${VB} ${VB}`);
    refPaths = Array.from(refSvg.querySelectorAll('path'));
    refPaths.forEach((p) => {
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke-width', '3');
      p.setAttribute('stroke-linecap', 'round');
      p.setAttribute('stroke-linejoin', 'round');
    });

    ctx = canvas.getContext('2d');
    const size = Math.min(host.clientWidth, 480);
    canvas.width = size;
    canvas.height = size;
    host.style.width = host.style.height = `${size}px`;

    ready = true;
    applyMode();
  });

  onDestroy(() => clearAnim());
</script>

<div class="wrap" class:animate-mode={mode === 'animate'}>
  <div class="stage" bind:this={host}></div>
  <canvas
    bind:this={canvas}
    onpointerdown={onDown}
    onpointermove={onMove}
    onpointerup={onUp}
    onpointercancel={onUp}
  ></canvas>
</div>
<div class="row">
  {#if mode === 'animate'}
    <button onclick={playAnimation} disabled={animating}>{animating ? 'Playing…' : '↻ Replay'}</button>
  {:else}
    <button onclick={reset}>Reset</button>
    <span class="fb">{feedback}</span>
  {/if}
</div>

<style>
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
  .animate-mode canvas { pointer-events: none; }
  .row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin-top: 1rem;
  }
  .fb {
    color: var(--fg-dim);
    font-variant-numeric: tabular-nums;
    min-width: 12rem;
    text-align: left;
    font-size: 0.9rem;
  }
</style>
