<script lang="ts">
  import { onMount } from 'svelte';
  import { normalizeToBox, pathToPoints, scoreStroke, type Point } from '../stroke/compare';

  interface Props {
    svg: string; // inline KanjiVG <svg> markup
  }
  const { svg }: Props = $props();

  let host: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null = null;
  let refPaths: SVGPathElement[] = [];
  let currentStroke = 0;
  let feedback = $state<string>('');
  let drawing = false;
  let userPoints: Point[] = [];

  // KanjiVG uses a 109x109 viewBox.
  const VB = 109;

  function resetPractice() {
    currentStroke = 0;
    feedback = '';
    clearCanvas();
    updateRefVisibility();
  }

  function clearCanvas() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function updateRefVisibility() {
    refPaths.forEach((p, i) => {
      if (i < currentStroke) {
        p.setAttribute('stroke', 'var(--fg-dim)');
        p.setAttribute('opacity', '0.45');
      } else if (i === currentStroke) {
        p.setAttribute('stroke', 'var(--accent-dim)');
        p.setAttribute('opacity', '0.35');
        p.setAttribute('stroke-dasharray', '3 2');
      } else {
        p.setAttribute('opacity', '0');
      }
    });
  }

  function canvasPoint(e: PointerEvent): Point {
    const rect = canvas.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * VB, y: ((e.clientY - rect.top) / rect.height) * VB };
  }

  function onDown(e: PointerEvent) {
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

    // draw scaled to actual pixel size
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / VB;
    const sy = canvas.height / VB;
    ctx.strokeStyle = '#ff7a59';
    ctx.lineWidth = Math.max(4, rect.width / 28);
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
    const refPoints = pathToPoints(ref, 32);
    const refNorm = normalizeToBox(refPoints, VB, VB);
    const userNorm = normalizeToBox(userPoints, VB, VB);
    const score = scoreStroke(userNorm, refNorm);
    if (score.pass) {
      feedback = `✓ stroke ${currentStroke + 1}`;
      currentStroke += 1;
      updateRefVisibility();
      if (currentStroke >= refPaths.length) feedback = '✓ complete!';
    } else {
      feedback = `retry (dot ${score.directionDot.toFixed(2)}, dist ${score.meanDistance.toFixed(2)})`;
    }
  }

  onMount(() => {
    host.innerHTML = svg;
    const svgEl = host.querySelector('svg');
    if (!svgEl) return;
    svgEl.setAttribute('width', '100%');
    svgEl.setAttribute('height', '100%');
    svgEl.setAttribute('viewBox', `0 0 ${VB} ${VB}`);
    refPaths = Array.from(svgEl.querySelectorAll('path'));
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

    resetPractice();
  });
</script>

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
<div class="row">
  <button onclick={resetPractice}>Reset</button>
  <span class="fb">{feedback}</span>
</div>

<style>
  .wrap {
    position: relative;
    width: min(80vw, 480px);
    aspect-ratio: 1 / 1;
    margin: 0 auto;
    background: var(--bg-alt);
    border-radius: 16px;
    border: 1px solid var(--border);
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
  .row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin-top: 0.75rem;
  }
  .fb {
    color: var(--fg-dim);
    font-variant-numeric: tabular-nums;
    min-width: 12rem;
    text-align: left;
  }
</style>
