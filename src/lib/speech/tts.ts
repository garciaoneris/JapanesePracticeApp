import { synthesizeJa } from './voicevox';

let voicesReady: Promise<SpeechSynthesisVoice[]> | null = null;

function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  if (voicesReady) return voicesReady;
  voicesReady = new Promise((resolve) => {
    const synth = window.speechSynthesis;
    const now = synth.getVoices();
    if (now.length) {
      resolve(now);
      return;
    }
    const handler = () => {
      synth.removeEventListener('voiceschanged', handler);
      resolve(synth.getVoices());
    };
    synth.addEventListener('voiceschanged', handler);
    // Fallback: some browsers never fire the event.
    setTimeout(() => resolve(synth.getVoices()), 1500);
  });
  return voicesReady;
}

async function pickJapaneseVoice(): Promise<SpeechSynthesisVoice | null> {
  const voices = await loadVoices();
  const ja = voices.filter((v) => v.lang.toLowerCase().startsWith('ja'));
  if (!ja.length) return null;
  return ja.find((v) => v.name.includes('Kyoko')) ?? ja.find((v) => v.name.includes('Otoya')) ?? ja[0];
}

/** The original iPad-TTS path — kept around as a fallback for when VOICEVOX
 * is offline/unreachable, and as the primary path when `navigator.onLine` is
 * false. Fire-and-forget: returns immediately, speech happens in background. */
function speakJaNative(text: string, rate = 0.95): void {
  if (!('speechSynthesis' in window)) return;
  pickJapaneseVoice().then((voice) => {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'ja-JP';
    utter.rate = rate;
    if (voice) utter.voice = voice;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  });
}

/** Keep track of the currently-playing VOICEVOX audio so a new call can
 * interrupt the previous one (matches native speech's cancel-on-new behavior). */
let activeAudio: HTMLAudioElement | null = null;

/**
 * Speak Japanese text. Tries VOICEVOX via a public proxy for high-quality
 * neural voices, falling back to the built-in iPad/browser TTS on any failure
 * or when offline. Must still be called from a user-gesture handler on iOS
 * for the first utterance in the session (same rule as before).
 */
export async function speakJa(text: string, rate = 0.95): Promise<void> {
  // Offline short-circuit — don't waste a 4s timeout on a hopeless fetch.
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    speakJaNative(text, rate);
    return;
  }

  try {
    const audio = await synthesizeJa(text);
    audio.playbackRate = rate;

    // Stop any audio still playing from a previous call before starting this one.
    if (activeAudio) {
      try { activeAudio.pause(); } catch {
        /* ignore */
      }
    }
    activeAudio = audio;

    await audio.play();
    await new Promise<void>((resolve) => {
      const done = () => {
        audio.removeEventListener('ended', done);
        audio.removeEventListener('error', done);
        if (activeAudio === audio) activeAudio = null;
        resolve();
      };
      audio.addEventListener('ended', done);
      audio.addEventListener('error', done);
    });
  } catch {
    speakJaNative(text, rate);
  }
}

export function ttsSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}
