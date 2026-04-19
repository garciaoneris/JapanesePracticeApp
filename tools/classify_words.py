"""Use the local vLLM server to classify each word in the bundle by
modern-use frequency tier (A/B/C/D/E). Drives a trial run over a random
sample first, prints results for human inspection; full-corpus mode
writes a {word_id: label} JSONL cache.

  # Trial — classify 100 random bundle words, print labeled list.
  python tools/classify_words.py --limit 100 --print

  # Full — classify every "common" JMdict word (pre-nf-filter), cache
  # the labels. Takes ~15-20 min at concurrency 12 for 23k words.
  python tools/classify_words.py --all --out tools/_data/word_labels.jsonl

The bundle-filter integration is a separate step: once labels exist,
edit parse_jmdict to drop D/E-labeled entries.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

import httpx
import orjson

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).parent))
from build_bundle import parse_jmdict, parse_kanjidic  # noqa: E402

VLLM_URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"

SYSTEM_PROMPT = """You classify Japanese words by how often a modern native speaker actually uses them. Judge by REAL-WORLD REGISTER, not the visual complexity of the kanji. Many words have archaic kanji verb forms (持て成す) that are rarely written — but the same word as hiragana or a noun (もてなし) is common. When in doubt, ask: "Would a 30-year-old Japanese person say this in 2024 on social media, in an email, or on TV?"

Labels:

A = Everyday common. Said in casual conversation, written in emails, texted, heard on TV. A learner needs this. Examples: 泥棒 thief, 教会 church, 口座 account, 病気 illness, 増える to increase, 電車 train, 人気 popularity, 大事 important, 簡単 easy, 動物 animal, 持て成す to entertain (guest), 挙句 "after all that" idiom, 横着 lazy, 下らない trivial, 虎 tiger, 鹿 deer.

B = Standard written / news / formal speech. Appears in newspapers, business documents, formal conversation, university lectures. A learner will read these often but rarely SAY them casually. Examples: 論点 argument-point, 支障 obstacle, 政党 political party, 解決 resolution, 合理的 rational, 抑止 deterrence, 認可 approval, 政局 political situation, 未婚 unmarried, 修正 revision, 識別 identification.

C = Technical / specialized jargon. Only used in a specific profession or academic field (law, medicine, finance, hard science, engineering, military, specific sport). A generalist reader wouldn't know the word. Examples: 刑法 criminal law, 窃盗 theft (legal term), 軍縮 disarmament, 転移 metastasis, 監事 auditor, 艦艇 warship, 財政投融資 Fiscal Investment Program, 先物 commodity futures, 滑走路 airport runway, 口頭弁論 oral court proceedings.

D = Dated / literary / overly formal. This is the TRICKY category. Criteria:
  - A modern speaker would use a DIFFERENT more common word for the same meaning.
  - Appears mostly in classical literature, old novels, stock idioms, or archaic writing.
  - Sounds like something an elderly person, a priest, or a pre-WWII novel would say.
Examples: 子女 sons-and-daughters (modern: 子供), 異邦人 foreigner (biblical; modern: 外国人), 感興 literary "interest" (modern: 興味), 名句 famous saying (modern: 名言), 青雲 literary "blue sky" (modern: 青空), 手塩 archaic "table salt" (idiom only: 手塩にかける), 如実 literary "reality", 施政 formal "governance" (modern: 政治), 杜撰 literary "sloppy" (modern: いい加減), 西方 literary "west" (modern: 西), 太り肉 archaic "plump", 感慨無量 literary yojijukugo, 百家争鳴 literary yojijukugo, 攻め立てる literary "to assault", 所期 archaic "expected".

E = Niche / very specific / proper-noun-ish. Specific organizations, regions, historical events, religions, defunct institutions, hobbies, obscure rituals. Even native speakers may not recognize it without context. Examples: 大本山 Buddhist head-temple, 落語家 rakugo storyteller, 創価学会 Soka Gakkai (org name), 文部省 defunct ministry, 中越 specific Niigata region, 二七日 Buddhist memorial service, 一石 a move in go, 五十三次 53 post stations on old highway, 見切り発車 idiom-only sports phrase.

Key decision boundaries:
  • A vs B: Would a casual tweet use this? → A. Only news/essays? → B.
  • B vs C: Does a non-specialist reader understand it? Yes → B. Needs field knowledge → C.
  • B vs D: Is the word ACTIVE in modern writing (newspaper, blog, manga) → B. Mostly archaic / appears only in stock idioms → D.
  • D vs E: Is it an abstract dated-concept → D. Is it a proper noun or field-specific artifact → E.

Respond with exactly ONE character: A, B, C, D, or E. Nothing else."""


async def classify_one(
    client: httpx.AsyncClient,
    jp: str,
    reading: str,
    meaning: str,
) -> str:
    resp = await client.post(
        VLLM_URL,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Word: {jp}\nReading: {reading}\nMeaning: {meaning}"},
            ],
            "temperature": 0.0,
            "max_tokens": 3,
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip().upper()
    for ch in raw:
        if ch in "ABCDE":
            return ch
    return "?"


async def trial_sample(
    bundle_path: Path,
    limit: int,
    concurrency: int,
    show: bool,
) -> None:
    bundle = orjson.loads(bundle_path.read_bytes())
    words = list(bundle["words"].values())
    random.seed(20260420)
    sample = random.sample(words, min(limit, len(words)))

    print(f"Classifying {len(sample)} random words via vLLM…")
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[str, str, str, str]] = []  # (jp, reading, meaning, label)

    async with httpx.AsyncClient() as client:
        async def worker(w: dict) -> None:
            async with sem:
                jp = w.get("jp", "")
                r = w.get("reading", "")
                m = (w.get("meanings") or [""])[0]
                label = await classify_one(client, jp, r, m)
                results.append((jp, r, m, label))

        t0 = time.perf_counter()
        await asyncio.gather(*(worker(w) for w in sample))
        dt = time.perf_counter() - t0

    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "?": 0}
    for _, _, _, label in results:
        counts[label] = counts.get(label, 0) + 1

    if show:
        for label in "ABCDE?":
            group = [(jp, r, m) for jp, r, m, lbl in results if lbl == label]
            if not group:
                continue
            print(f"\n=== {label} — {len(group)} words ===")
            for jp, r, m in sorted(group):
                print(f"  {jp:10s}  {r:12s}  {m}")
    total = len(results)
    print(f"\n{total} classified in {dt:.1f}s ({total/dt:.1f} it/s)")
    for label in "ABCDE?":
        c = counts[label]
        print(f"  {label}: {c:4d}  {100*c/total:5.1f}%")


async def full_corpus(
    data_dir: Path,
    out_path: Path,
    concurrency: int,
) -> None:
    """Classify every common-tagged kanji word in JMdict (pre-nf-filter).
    Writes JSONL: {id, jp, reading, meaning, label}."""
    kanji = parse_kanjidic(data_dir / "kanjidic2.xml")
    # Temporarily bypass our own nf filter so we see ALL common-tagged words
    # — the whole point is to let the LLM choose without the heuristic.
    from build_bundle import NF_FREQUENCY_CUTOFF  # noqa: PLC0415
    import build_bundle  # noqa: PLC0415
    build_bundle.NF_FREQUENCY_CUTOFF = 99  # keep everything
    words = parse_jmdict(data_dir / "JMdict_e", set(kanji.keys()), set())
    build_bundle.NF_FREQUENCY_CUTOFF = NF_FREQUENCY_CUTOFF  # restore
    # Load already-classified so we can resume.
    already: set[str] = set()
    if out_path.exists():
        with out_path.open("rb") as f:
            for raw in f:
                if raw.strip():
                    try:
                        already.add(str(orjson.loads(raw).get("id", "")))
                    except orjson.JSONDecodeError:
                        pass
    pending = [w for w in words.values() if w.id not in already and w.jp]
    print(f"Already classified: {len(already)}   pending: {len(pending)}")
    sem = asyncio.Semaphore(concurrency)
    t0 = time.perf_counter()
    done = 0
    async with httpx.AsyncClient() as client:
        async def worker(w) -> None:  # type: ignore[no-untyped-def]
            nonlocal done
            async with sem:
                try:
                    m = w.meanings[0] if w.meanings else ""
                    label = await classify_one(client, w.jp, w.reading, m)
                except Exception:  # noqa: BLE001
                    label = "?"
                with out_path.open("ab") as f:
                    f.write(orjson.dumps({
                        "id": w.id,
                        "jp": w.jp,
                        "reading": w.reading,
                        "meaning": m,
                        "label": label,
                    }))
                    f.write(b"\n")
                done += 1
                if done % 200 == 0:
                    rate = done / (time.perf_counter() - t0)
                    eta = (len(pending) - done) / max(rate, 0.01)
                    print(f"  {done}/{len(pending)}  {rate:.1f} it/s  ETA {eta/60:.1f} min")
        await asyncio.gather(*(worker(w) for w in pending))
    print(f"Done. {done}/{len(pending)} in {(time.perf_counter()-t0)/60:.1f} min")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", type=Path, default=Path("public/data/bundle.json"))
    ap.add_argument("--data-dir", type=Path, default=Path("tools/_data"))
    ap.add_argument("--out", type=Path, default=Path("tools/_data/word_labels.jsonl"))
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--limit", type=int, default=100, help="trial-sample size")
    ap.add_argument("--print", dest="show", action="store_true", help="show labeled list")
    ap.add_argument("--all", action="store_true", help="classify entire common JMdict corpus, write to --out")
    args = ap.parse_args()

    if args.all:
        asyncio.run(full_corpus(args.data_dir, args.out, args.concurrency))
    else:
        asyncio.run(trial_sample(args.bundle, args.limit, args.concurrency, args.show))


if __name__ == "__main__":
    main()
