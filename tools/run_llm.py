"""Driver: iterate every JMdict word we keep in the bundle, ask the LLM for a
sentence, and append validated results to tools/_data/llm_word_cache.jsonl.

Resume-safe: re-running skips any word id already in the cache. Append-only
writes are fsynced after every entry so Ctrl+C loses at most one in-flight
request.

Typical vLLM run:
    python -m vllm.entrypoints.openai.api_server \\
      --model Qwen/Qwen2.5-7B-Instruct-AWQ \\
      --max-model-len 4096 --gpu-memory-utilization 0.85 \\
      --host 127.0.0.1 --port 8000

    python tools/run_llm.py --backend vllm --concurrency 32

Smoke test first:
    python tools/run_llm.py --backend vllm --concurrency 4 --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
import orjson
from tqdm.asyncio import tqdm as atqdm

# Reuse parsers + dataclasses from the existing build script.
sys.path.insert(0, str(Path(__file__).parent))
from build_bundle import parse_jmdict, parse_kanjidic  # noqa: E402
from llm_generate import (  # noqa: E402
    allowed_kanji_for_word,
    generate_word_example,
)

CACHE_PATH = Path("tools/_data/llm_word_cache.jsonl")


def load_cache() -> dict[str, dict[str, object]]:
    """Read the JSONL cache into a dict keyed by word id. Malformed lines
    are skipped with a warning so a partial crash during write can't brick
    the whole cache."""
    out: dict[str, dict[str, object]] = {}
    if not CACHE_PATH.exists():
        return out
    with CACHE_PATH.open("rb") as f:
        for ln, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                row = orjson.loads(raw)
            except orjson.JSONDecodeError:
                print(f"[cache] skipping malformed line {ln}", file=sys.stderr)
                continue
            wid = str(row.get("id", ""))
            if wid:
                out[wid] = row
    return out


def append_cache(row: dict[str, object]) -> None:
    """Append one JSON object as a single line, then fsync. Survives Ctrl+C."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("ab") as f:
        f.write(orjson.dumps(row))
        f.write(b"\n")
        f.flush()
        import os

        os.fsync(f.fileno())


async def run(
    *,
    backend: str,
    model: str,
    concurrency: int,
    limit: int | None,
    data_dir: Path,
) -> None:
    print(f"Parsing KANJIDIC2 and JMdict from {data_dir}…")
    t0 = time.perf_counter()
    kanji = parse_kanjidic(data_dir / "kanjidic2.xml")
    words = parse_jmdict(data_dir / "JMdict_e", set(kanji.keys()), set())
    print(
        f"  loaded {len(kanji)} kanji, {len(words)} words "
        f"in {time.perf_counter() - t0:.1f}s"
    )

    cache = load_cache()
    print(f"Cache at {CACHE_PATH} has {len(cache)} entries")

    pending = [w for w in words.values() if w.id not in cache]
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        print("Nothing to do — all words cached.")
        return

    print(
        f"Will generate {len(pending)} entries via {backend} "
        f"(concurrency={concurrency})"
    )

    # Effective concurrency: Ollama serves one request at a time per model
    # instance, so keep the semaphore at 1 for it. vLLM batches.
    effective_conc = concurrency if backend == "vllm" else 1
    sem = asyncio.Semaphore(effective_conc)

    failures: list[tuple[str, str, str]] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:

        async def worker(w) -> None:  # type: ignore[no-untyped-def]
            async with sem:
                allowed = allowed_kanji_for_word(list(w.kanji), kanji)
                # The target word's own kanji are always allowed (some words
                # sit at their level's ceiling; the set already includes
                # them, but belt-and-suspenders in case of kana-only words).
                allowed.update(w.kanji)
                meaning = w.meanings[0] if w.meanings else ""
                try:
                    ex, _errs = await generate_word_example(
                        client=client,
                        backend=backend,
                        model=model,
                        word_jp=w.jp,
                        reading=w.reading,
                        meaning=meaning,
                        allowed_kanji=allowed,
                    )
                except Exception as exc:
                    failures.append((w.id, w.jp, str(exc)))
                    return

                append_cache({
                    "id": w.id,
                    "jp": w.jp,
                    "sentence_jp": ex.sentence_jp,
                    "sentence_en": ex.sentence_en,
                    "segs": [s.model_dump(exclude_none=True) for s in ex.segs],
                })

        tasks = [asyncio.create_task(worker(w)) for w in pending]
        for _ in atqdm.as_completed(tasks, total=len(tasks), desc="words"):
            await _  # noqa: F841 — we just want the progress bar

    print()
    print(f"Done. {len(pending) - len(failures)} new entries, {len(failures)} failed.")
    if failures:
        print("Sample failures:")
        for wid, jp, msg in failures[:10]:
            print(f"  {wid} {jp}: {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backend",
        choices=["vllm", "ollama"],
        default="vllm",
        help="Which local LLM server to hit. vLLM batches and is ~50x faster.",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="Model identifier. Defaults: Qwen/Qwen2.5-7B-Instruct-AWQ for vllm, qwen2.5:7b for ollama.",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=32,
        help="Concurrent in-flight requests (vLLM only; Ollama forced to 1).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N pending words (smoke test).",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=Path("tools/_data"),
    )
    args = ap.parse_args()

    model = args.model or (
        "Qwen/Qwen2.5-7B-Instruct-AWQ" if args.backend == "vllm" else "qwen2.5:7b"
    )

    try:
        asyncio.run(
            run(
                backend=args.backend,
                model=model,
                concurrency=args.concurrency,
                limit=args.limit,
                data_dir=args.data_dir,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted — partial cache is preserved. Re-run to resume.")


if __name__ == "__main__":
    main()
