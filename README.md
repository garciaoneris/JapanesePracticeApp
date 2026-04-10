# Japanese Practice PWA

Practice Japanese vocabulary and kanji on anything with a modern browser. Ships as a Progressive Web App.

## What it does

- Browse ~300 JLPT N5 + N4 kanji, each with animated stroke order (KanjiVG).
- Draw strokes with an Apple Pencil or finger; the app validates direction, shape, and length against the reference.
- Tap any reading to hear it via the OS Japanese TTS voice (Kyoko / Otoya on iPadOS).
- Practice pronunciation: tap the mic, say the reading, and get a hiragana-normalized match score via the Web Speech API.
- Spaced repetition review queue (SM-2 variant) for mixed kanji + vocab cards.
- Fully offline after first load (service worker + IndexedDB).

## Stack

- Vite + Svelte 5 + TypeScript
- `vite-plugin-pwa` (Workbox) for the service worker and install manifest
- `idb` wrapping IndexedDB for dictionary + SRS state
- Inline KanjiVG SVG + `<canvas>` overlay with Pointer Events
- Python + `lxml` for the one-time dataset build

## First-time setup (Windows)

```powershell
# Node side
npm install

# Python side (only needed to rebuild the dictionary bundle)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r tools/requirements.txt
```

## Building the dictionary bundle

Download these source files into `tools/_data/` (one-time; they're large and redistributable but not bundled here):

| File | Source |
|---|---|
| `kanjidic2.xml` | https://www.edrdg.org/wiki/index.php/KANJIDIC_Project |
| `kanjivg-YYYYMMDD.xml` | https://kanjivg.tagaini.net/ |
| `JMdict_e` | https://www.edrdg.org/jmdict/j_archive.html |
| `sentences.csv` + `links.csv` | https://tatoeba.org/en/downloads (filtered: jpn + eng) |
| `jlpt_n4_n5_vocab.txt` | Tanos JLPT lists, one word per line (optional — smaller bundle if present) |

Then:

```powershell
python tools/build_bundle.py --validate
```

This writes `public/data/bundle.json`. The PWA loads it once on first run and copies it into IndexedDB, so later visits are fully offline.

## Dev loop

```powershell
npm run dev
```

Desktop Chrome supports both `speechSynthesis` and `webkitSpeechRecognition`, so you can iterate speech features on Windows. The final voice list and STT behavior are iPad-specific — always do a smoke test on the real device.

Use DevTools → Application → Service Workers → "Offline" to verify offline mode.

## Deploying to GitHub Pages

1. Create a GitHub repo named `JapanesePracticeApp` and push this directory to `main`.
2. Repo → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Push. `.github/workflows/deploy.yml` builds and deploys `dist/` to Pages automatically.
4. The site will be live at `https://<your-user>.github.io/JapanesePracticeApp/`.

The workflow sets `APP_BASE=/JapanesePracticeApp/` at build time so asset URLs and the service-worker scope match the subpath. An empty `public/.nojekyll` prevents GitHub from stripping files that start with `_`.

**Commit `public/data/bundle.json`**. It's a few MB and avoids running the Python pipeline in CI. If you'd rather build it in CI, add a step before `npm run build` that runs `python tools/build_bundle.py` with the source files fetched from somewhere (they are not freely redistributable inside a repo on GitHub without attribution — check each license first).


## Licenses of bundled dictionary sources

- **KanjiVG** — CC BY-SA 3.0
- **KANJIDIC2** — CC BY-SA 4.0 (EDRDG)
- **JMdict** — CC BY-SA 4.0 (EDRDG)
- **Tatoeba** — CC BY 2.0 FR

If you publish the built bundle, surface a notice in the app (e.g. on an About page) crediting these sources. Not done yet in the MVP.
