# `tools/` — bundle build pipeline

## Overview

`build_bundle.py` emits `public/data/bundle.json`, the single data file the PWA
loads on first run. It parses KANJIDIC2, KanjiVG, and JMdict; picks the vocab
set we ship; and attaches example sentences.

Two example-sentence backends:

| Backend | Source | Speed | Quality of furigana |
|---|---|---|---|
| **Tatoeba + fugashi** (default) | `jpn_sentences.tsv`, `eng_sentences.tsv`, `jpn_eng_links.tsv` | fast (~30 s) | good on simple sentences, unreliable on compounds (UniDic-lite picks wrong word boundaries) |
| **LLM** (`--use-llm`) | `llm_word_cache.jsonl` (produced by `run_llm.py`) | depends on backend below | consistently accurate — sentence, reading, and glosses come from the same JSON payload so they can't disagree |

## Source data

Place these under `tools/_data/` (all unzipped):

- `kanjivg-YYYYMMDD.xml` — KanjiVG stroke data
- `kanjidic2.xml` — KANJIDIC2
- `JMdict_e` — JMdict English-only
- `jpn_sentences.tsv`, `eng_sentences.tsv`, `jpn_eng_links.tsv` — Tatoeba
  (only needed if you're not using `--use-llm`)
- `jlpt_n4_n5_vocab.txt` — optional vocab whitelist

Sources:
- KanjiVG:   <https://kanjivg.tagaini.net/>
- KANJIDIC2: <https://www.edrdg.org/wiki/index.php/KANJIDIC_Project>
- JMdict:    <https://www.edrdg.org/jmdict/j_archive.html>
- Tatoeba:   <https://tatoeba.org/en/downloads>

## Default (Tatoeba + fugashi) build

```bash
pip install -r tools/requirements.txt
python tools/build_bundle.py --validate
```

Writes to `public/data/bundle.json`. Reports per-phase timings and final size.

## LLM-driven build (vLLM + Qwen2.5 7B AWQ)

### One-time setup

```bash
pip install vllm
```

Start the vLLM server in a background terminal (first run downloads the
model, ~4.5 GB):

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct-AWQ \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  --host 127.0.0.1 --port 8000
```

On an RTX 3060 Ti (8 GB), the model loads in ~30 s. Verify with:

```bash
curl http://127.0.0.1:8000/v1/models
```

### Generate the per-word cache (resume-safe)

```bash
# Smoke-test first — 20 entries, visible in tools/_data/llm_word_cache.jsonl
python tools/run_llm.py --backend vllm --concurrency 4 --limit 20

# Then the full run — ~1–2 h on a 3060 Ti with AWQ:
python tools/run_llm.py --backend vllm --concurrency 32
```

Safe to Ctrl+C and re-run. The cache appends one line per generated word.
Each line:

```json
{"id":"1578850","jp":"行く","sentence_jp":"学校に行く。","sentence_en":"I go to school.","segs":[{"t":"学校","r":"がっこう","g":"school"},{"t":"に"},{"t":"行く","r":"いく","g":"to go"},{"t":"。"}]}
```

### Ollama fallback (for debugging — much slower)

```bash
ollama pull qwen2.5:7b
python tools/run_llm.py --backend ollama --limit 5
```

Ollama serves one request at a time per model, so concurrency is forced to
1. Realistic only for small batches.

### Build the bundle with LLM examples

```bash
python tools/build_bundle.py --use-llm --validate
```

This skips the entire Tatoeba + fugashi pipeline; every word's example comes
from the cache. Words missing from the cache get an empty examples list (the
frontend hides the example UI gracefully).

Remember to bump `EXPECTED_VERSION` in `src/lib/data/bundle.ts` if you
haven't already — cached clients need to refetch.

## Validation what the LLM emits

`llm_generate.py` rejects any response that violates:

1. `sentence_jp` must contain the target word verbatim.
2. Every kanji in `sentence_jp` must be in the word's allowed set
   (word's level or lower — see `allowed_kanji_for_word`).
3. Concatenating `segs[*].t` must reproduce `sentence_jp` exactly.
4. Every seg that contains kanji must have a hiragana `r` (no katakana, no
   kanji, no latin letters in the reading).

On violation the runner retries up to 3 times, adding a short "your previous
answer broke rule X" note to the prompt so the model self-corrects. After 3
failures the word is skipped and logged.
