export type Point = { x: number; y: number };

export function resample(points: Point[], n: number): Point[] {
  if (points.length < 2) return points.slice();
  const lengths: number[] = [0];
  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    lengths.push(lengths[i - 1] + Math.hypot(dx, dy));
  }
  const total = lengths[lengths.length - 1];
  if (total === 0) return Array.from({ length: n }, () => ({ ...points[0] }));
  const step = total / (n - 1);
  const out: Point[] = [points[0]];
  let j = 1;
  for (let i = 1; i < n - 1; i++) {
    const target = i * step;
    while (j < lengths.length - 1 && lengths[j] < target) j++;
    const t = (target - lengths[j - 1]) / (lengths[j] - lengths[j - 1] || 1);
    out.push({
      x: points[j - 1].x + t * (points[j].x - points[j - 1].x),
      y: points[j - 1].y + t * (points[j].y - points[j - 1].y),
    });
  }
  out.push(points[points.length - 1]);
  return out;
}

export function pathToPoints(path: SVGPathElement, n: number): Point[] {
  const total = path.getTotalLength();
  const out: Point[] = [];
  for (let i = 0; i < n; i++) {
    const p = path.getPointAtLength((i / (n - 1)) * total);
    out.push({ x: p.x, y: p.y });
  }
  return out;
}

export function normalizeToBox(points: Point[], width: number, height: number): Point[] {
  return points.map((p) => ({ x: p.x / width, y: p.y / height }));
}

function length(points: Point[]): number {
  let s = 0;
  for (let i = 1; i < points.length; i++) {
    s += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  }
  return s;
}

function direction(points: Point[]): Point {
  const a = points[0];
  const b = points[points.length - 1];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const m = Math.hypot(dx, dy) || 1;
  return { x: dx / m, y: dy / m };
}

export interface StrokeScore {
  pass: boolean;
  meanDistance: number;
  directionDot: number;
  lengthRatio: number;
}

export function scoreStroke(user: Point[], reference: Point[]): StrokeScore {
  const N = 32;
  const u = resample(user, N);
  const r = resample(reference, N);

  let sum = 0;
  for (let i = 0; i < N; i++) {
    sum += Math.hypot(u[i].x - r[i].x, u[i].y - r[i].y);
  }
  const meanDistance = sum / N;

  const du = direction(u);
  const dr = direction(r);
  const directionDot = du.x * dr.x + du.y * dr.y;

  const lu = length(u);
  const lr = length(r) || 1;
  const lengthRatio = lu / lr;

  const pass = directionDot > 0.7 && meanDistance < 0.15 && lengthRatio > 0.5 && lengthRatio < 2.0;
  return { pass, meanDistance, directionDot, lengthRatio };
}
