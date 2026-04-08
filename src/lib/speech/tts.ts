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

/**
 * Speak Japanese text. Must be called from a user-gesture handler on iOS Safari
 * for the first utterance in the session.
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
