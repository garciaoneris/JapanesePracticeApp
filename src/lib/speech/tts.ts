import { getMeta, putMeta } from '../data/db';

let preferredLoaded = false;
let preferredVoiceName: string | null = null;

// iPadOS 16 Safari quirk: getVoices() often returns [] until a speak() has
// occurred, and voiceschanged may fire late or never. Poll for up to 5s and
// never cache an empty result.
function loadVoices(timeoutMs = 5000): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      resolve([]);
      return;
    }
    const synth = window.speechSynthesis;
    const now = synth.getVoices();
    if (now.length) {
      resolve(now);
      return;
    }
    let done = false;
    const finish = (v: SpeechSynthesisVoice[]) => {
      if (done) return;
      done = true;
      synth.removeEventListener('voiceschanged', onChange);
      clearInterval(poll);
      clearTimeout(bail);
      resolve(v);
    };
    const onChange = () => {
      const v = synth.getVoices();
      if (v.length) finish(v);
    };
    synth.addEventListener('voiceschanged', onChange);
    const poll = setInterval(() => {
      const v = synth.getVoices();
      if (v.length) finish(v);
    }, 200);
    const bail = setTimeout(() => finish(synth.getVoices()), timeoutMs);
  });
}

export async function listJapaneseVoices(): Promise<SpeechSynthesisVoice[]> {
  const voices = await loadVoices();
  return voices.filter((v) => v.lang.toLowerCase().startsWith('ja'));
}

// User-gesture kick: some iOS/iPadOS versions only populate getVoices() after
// a speak() has fired. Speak a silent/short utterance then re-poll.
export async function kickVoiceLoad(): Promise<SpeechSynthesisVoice[]> {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return [];
  try {
    // Audible short utterance so the user gets feedback that TTS works, even
    // if getVoices() stays empty (iPadOS 16 Safari never populates the list).
    const u = new SpeechSynthesisUtterance('テスト');
    u.lang = 'ja-JP';
    u.rate = 1;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch {
    // ignore
  }
  return listJapaneseVoices();
}

async function ensurePreferredLoaded(): Promise<void> {
  if (preferredLoaded) return;
  preferredLoaded = true;
  preferredVoiceName = (await getMeta<string>('tts-voice-name')) ?? null;
}

export async function getPreferredVoiceName(): Promise<string | null> {
  await ensurePreferredLoaded();
  return preferredVoiceName;
}

export async function setPreferredVoiceName(name: string | null): Promise<void> {
  preferredVoiceName = name && name.length > 0 ? name : null;
  preferredLoaded = true;
  await putMeta('tts-voice-name', preferredVoiceName);
}

async function pickJapaneseVoice(): Promise<SpeechSynthesisVoice | null> {
  const ja = await listJapaneseVoices();
  if (!ja.length) return null;
  await ensurePreferredLoaded();
  if (preferredVoiceName) {
    const match = ja.find((v) => v.name === preferredVoiceName);
    if (match) return match;
  }
  // Auto-selection order: Siri 2 (iPadOS 17+) → Kyoko → Otoya → first.
  return (
    ja.find((v) => /siri.*(?:voice\s*)?2/i.test(v.name)) ??
    ja.find((v) => v.name.includes('Kyoko')) ??
    ja.find((v) => v.name.includes('Otoya')) ??
    ja[0]
  );
}

/**
 * Speak Japanese text via the platform's built-in TTS. On iPadOS that's Kyoko
 * (female) or Otoya (male) — not the best quality in the world, but natural
 * enough and 100% offline. Must be called from a user-gesture handler on iOS
 * for the first utterance in the session.
 *
 * This used to route through VOICEVOX via a public proxy for higher-quality
 * neural voices, but the VOICEVOX voice cast is intentionally character /
 * anime-style (ずんだもん, 四国めたん, …) and doesn't suit adult learners.
 * If you ever want a natural-sounding online voice, Google Cloud TTS or
 * Azure Cognitive Services have neural Japanese voices (Kaori / Keita /
 * Nanami / Aoi) behind an API key — happy to wire one up on request.
 */
export async function speakJa(text: string, rate = 0.95): Promise<void> {
  if (!('speechSynthesis' in window)) return;
  const voice = await pickJapaneseVoice();
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = 'ja-JP';
  utter.rate = rate;
  if (voice) utter.voice = voice;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

export function ttsSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}
