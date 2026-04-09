/** VOICEVOX TTS via a public proxy.
 *
 * Uses the community-run `api.tts.quest` endpoint which wraps VOICEVOX-style
 * neural Japanese voices behind a CORS-enabled JSON API. No API key is
 * required (but if absent we're on a rate-limited free tier).
 *
 * The endpoint returns JSON with an `mp3StreamingUrl` we feed straight into
 * an HTMLAudioElement. iOS Safari still requires that `.play()` be triggered
 * from a user gesture — same rule as speechSynthesis — which the existing
 * call sites already respect.
 *
 * Speaker IDs (most common):
 *    1  = ずんだもん ノーマル    (default; clear and expressive)
 *    2  = 四国めたん ノーマル
 *    3  = ずんだもん あまあま
 *    8  = 春日部つむぎ ノーマル
 */

const PROXY = 'https://api.tts.quest/v3/voicevox/synthesis';
export const DEFAULT_SPEAKER = 1;
const TIMEOUT_MS = 4000;

interface ProxyResponse {
  success: boolean;
  mp3StreamingUrl?: string;
  mp3DownloadUrl?: string;
  wavDownloadUrl?: string;
}

/** Fetch a synthesized HTMLAudioElement ready to play. Throws on network
 * error, timeout, non-OK response, or missing audio URL. */
export async function synthesizeJa(
  text: string,
  opts: { speaker?: number; signal?: AbortSignal } = {},
): Promise<HTMLAudioElement> {
  const speaker = opts.speaker ?? DEFAULT_SPEAKER;
  const url = `${PROXY}?text=${encodeURIComponent(text)}&speaker=${speaker}`;

  // Wire up an AbortController for our own timeout if the caller didn't pass one.
  const controller = new AbortController();
  const signal = opts.signal ?? controller.signal;
  const timeoutId = window.setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(url, { signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`voicevox proxy ${res.status}`);
    const body = (await res.json()) as ProxyResponse;
    if (!body.success) throw new Error('voicevox proxy reported !success');

    const audioUrl = body.mp3StreamingUrl ?? body.mp3DownloadUrl ?? body.wavDownloadUrl;
    if (!audioUrl) throw new Error('voicevox proxy returned no audio URL');

    const audio = new Audio(audioUrl);
    audio.preload = 'auto';
    audio.crossOrigin = 'anonymous';

    // Wait until the browser has enough data to start playback, but don't
    // block forever on stragglers — the fallback path handles stalls.
    await new Promise<void>((resolve, reject) => {
      const onCanPlay = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error('audio element failed to load'));
      };
      const cleanup = () => {
        audio.removeEventListener('canplay', onCanPlay);
        audio.removeEventListener('error', onError);
      };
      audio.addEventListener('canplay', onCanPlay);
      audio.addEventListener('error', onError);
      // Safety net: if canplay never fires, reject so the caller can fall back.
      window.setTimeout(() => {
        cleanup();
        reject(new Error('audio canplay timeout'));
      }, TIMEOUT_MS);
    });

    return audio;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
