// Minimal typing for the non-standard webkit API.
interface SRConstructor {
  new (): SRInstance;
}
interface SRInstance {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: SREvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
}
interface SREvent {
  results: ArrayLike<{ 0: { transcript: string; confidence: number } }>;
}

function getCtor(): SRConstructor | null {
  const w = window as unknown as { webkitSpeechRecognition?: SRConstructor; SpeechRecognition?: SRConstructor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function sttSupported(): boolean {
  return getCtor() !== null;
}

export interface SttResult {
  transcript: string;
  confidence: number;
}

/**
 * Start a single-shot Japanese recognition. MUST be called directly from a
 * user gesture (click/touchend handler) on iOS Safari.
 */
export function recognizeJa(): Promise<SttResult> {
  return new Promise((resolve, reject) => {
    const Ctor = getCtor();
    if (!Ctor) {
      reject(new Error('SpeechRecognition not supported on this browser'));
      return;
    }
    const rec = new Ctor();
    rec.lang = 'ja-JP';
    rec.continuous = false;
    rec.interimResults = false;

    let settled = false;

    rec.onresult = (e) => {
      if (settled) return;
      settled = true;
      const top = e.results[0][0];
      resolve({ transcript: top.transcript, confidence: top.confidence });
    };
    rec.onerror = (e) => {
      if (settled) return;
      settled = true;
      reject(new Error(`stt error: ${e.error}`));
    };
    rec.onend = () => {
      if (settled) return;
      settled = true;
      reject(new Error('stt ended with no result'));
    };

    try {
      rec.start();
    } catch (err) {
      reject(err);
    }
  });
}

// Normalize a Japanese string for scoring: strip spaces, map katakana to hiragana.
export function normalizeKana(s: string): string {
  const stripped = s.replace(/[\s\u3000]/g, '');
  let out = '';
  for (const ch of stripped) {
    const code = ch.codePointAt(0)!;
    // Katakana (U+30A1–U+30F6) → Hiragana by subtracting 0x60.
    if (code >= 0x30a1 && code <= 0x30f6) out += String.fromCodePoint(code - 0x60);
    else out += ch;
  }
  return out;
}

export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const prev = new Array<number>(b.length + 1);
  const curr = new Array<number>(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
  }
  return prev[b.length];
}

export function kanaMatchScore(expected: string, heard: string): number {
  const e = normalizeKana(expected);
  const h = normalizeKana(heard);
  if (!e.length) return 0;
  const dist = levenshtein(e, h);
  return Math.max(0, 1 - dist / e.length);
}
