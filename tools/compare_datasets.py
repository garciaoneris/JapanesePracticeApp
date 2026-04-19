"""Side-by-side quality comparison of two example-sentence datasets:

  A. Tatoeba+fugashi (current public/data/bundle.json, version 7)
  B. LLM-generated (tools/_data/llm_word_cache.jsonl, destined for v8)

Samples the same N words from both and scores each example on:

  * READING ACCURACY — for every seg that contains kanji, is seg.r a valid
    JMdict reading for seg.t? If not, is it at least plausible hiragana
    (fugashi agrees)? If not, it's wrong.
  * LEVEL APPROPRIATENESS — does the sentence stay within the target word's
    curriculum level (all kanji at level ≤ word_level)?
  * STRUCTURAL VALIDITY — target word appears in sentence; segs concatenate
    to sentence; no Latin letters.

Prints per-dataset percentages + 5 side-by-side example contrasts so the
differences are concrete.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import orjson

sys.path.insert(0, str(Path(__file__).parent))
from build_bundle import parse_kanjidic  # noqa: E402
from fix_readings import (  # noqa: E402
    _is_kanji,
    build_jmdict_reading_lookup,
    fugashi_reading,
    has_kanji,
)
from llm_generate import LEVEL_OF_JLPT  # noqa: E402

# Force UTF-8 on Windows.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


ROOT = Path(__file__).resolve().parent.parent
TATOEBA_BUNDLE = ROOT / "public" / "data" / "bundle.json"
LLM_CACHE = ROOT / "tools" / "_data" / "llm_word_cache.jsonl"
JMDICT = ROOT / "tools" / "_data" / "JMdict_e"
KANJIDIC = ROOT / "tools" / "_data" / "kanjidic2.xml"

SAMPLE_SIZE = 200
SEED = 20260419


def load_tatoeba_examples() -> dict[str, dict]:
    """Return {word_id: {"jp":..., "sentence_jp":..., "sentence_en":..., "segs":[...], "kanji":[...]}}.
    Uses the first example of each word."""
    bundle = orjson.loads(TATOEBA_BUNDLE.read_bytes())
    words = bundle.get("words", {})
    out: dict[str, dict] = {}
    for wid, w in words.items():
        exs = w.get("examples") or []
        if not exs:
            continue
        ex = exs[0]
        segs = ex.get("segs") or []
        sentence_jp = "".join(s.get("t", "") for s in segs)
        out[str(wid)] = {
            "jp": w.get("jp", ""),
            "sentence_jp": sentence_jp,
            "sentence_en": ex.get("en", ""),
            "segs": segs,
            "kanji": w.get("kanji", []),
        }
    return out


def load_llm_examples() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with LLM_CACHE.open("rb") as f:
        for raw in f:
            if not raw.strip():
                continue
            try:
                row = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            wid = str(row.get("id", ""))
            if not wid:
                continue
            out[wid] = {
                "jp": row.get("jp", ""),
                "sentence_jp": row.get("sentence_jp", ""),
                "sentence_en": row.get("sentence_en", ""),
                "segs": row.get("segs") or [],
                "kanji": [c for c in str(row.get("jp", "")) if _is_kanji(c)],
            }
    return out


def score_reading(seg: dict, jm_lookup: dict[str, set[str]]) -> str:
    """Return one of: 'no-kanji', 'missing', 'correct', 'plausible', 'wrong'."""
    t = seg.get("t", "")
    if not has_kanji(t):
        return "no-kanji"
    r = seg.get("r")
    if not r:
        return "missing"
    # katakana / romaji / kanji in r → definitely wrong
    for c in r:
        cp = ord(c)
        if 0x30A1 <= cp <= 0x30F6:
            # Allow pure katakana reading only if the seg itself is a known
            # ateji surface (like 寿府→ジュネーブ) — but we filter those out,
            # so in practice this is always wrong.
            return "wrong"
        if _is_kanji(c):
            return "wrong"
        if c.isascii() and c.isalpha():
            return "wrong"
    jm = jm_lookup.get(t)
    if jm and r in jm:
        return "correct"
    # Not in JMdict but might be an inflected / compound form. Ask fugashi.
    fu = fugashi_reading(t)
    if fu == r:
        return "plausible"
    # Fugashi disagrees but maybe JMdict also has a close enough entry.
    if jm:
        return "wrong"  # surface is in dict but r isn't any known reading
    return "plausible"  # no dictionary signal; assume plausible


def score_level(
    sentence_jp: str,
    word_kanji: list[str],
    kanji_jlpt: dict[str, int],
) -> str:
    """Return 'within' / 'above' / 'no-kanji-in-sentence'."""

    def level_of(ch: str) -> int:
        jlpt = kanji_jlpt.get(ch)
        if jlpt is None:
            return 5
        return LEVEL_OF_JLPT.get(int(jlpt), 5)

    sent_kanji = [c for c in sentence_jp if _is_kanji(c)]
    if not sent_kanji:
        return "no-kanji-in-sentence"
    if word_kanji:
        word_level = max(level_of(c) for c in word_kanji)
    else:
        word_level = 5  # kana-only words: allow anything
    bad = [c for c in sent_kanji if level_of(c) > word_level]
    return "above" if bad else "within"


def score_structure(ex: dict) -> dict[str, bool]:
    sentence = ex.get("sentence_jp", "")
    jp = ex.get("jp", "")
    segs = ex.get("segs") or []
    concat = "".join(s.get("t", "") for s in segs)
    return {
        "has_target": jp in sentence,
        "segs_concat_ok": concat == sentence,
        "no_latin": not any(c.isascii() and c.isalpha() for c in sentence),
    }


def evaluate(
    examples: dict[str, dict],
    word_ids: list[str],
    jm_lookup: dict[str, set[str]],
    kanji_jlpt: dict[str, int],
) -> dict:
    totals = {
        "covered": 0,  # word_ids for which this dataset has an example
        "reading_kanji_segs": 0,
        "reading_correct": 0,
        "reading_plausible": 0,
        "reading_wrong": 0,
        "reading_missing": 0,
        "level_within": 0,
        "level_above": 0,
        "level_no_kanji": 0,
        "struct_has_target": 0,
        "struct_concat_ok": 0,
        "struct_no_latin": 0,
        "sent_len_sum": 0,
    }
    for wid in word_ids:
        ex = examples.get(wid)
        if ex is None or not ex.get("sentence_jp"):
            continue
        totals["covered"] += 1
        totals["sent_len_sum"] += len(ex["sentence_jp"])
        # Readings
        for seg in ex.get("segs") or []:
            res = score_reading(seg, jm_lookup)
            if res == "no-kanji":
                continue
            totals["reading_kanji_segs"] += 1
            if res == "correct":
                totals["reading_correct"] += 1
            elif res == "plausible":
                totals["reading_plausible"] += 1
            elif res == "missing":
                totals["reading_missing"] += 1
            else:
                totals["reading_wrong"] += 1
        # Level
        lv = score_level(ex["sentence_jp"], ex.get("kanji") or [], kanji_jlpt)
        if lv == "within":
            totals["level_within"] += 1
        elif lv == "above":
            totals["level_above"] += 1
        else:
            totals["level_no_kanji"] += 1
        # Structure
        st = score_structure(ex)
        if st["has_target"]:
            totals["struct_has_target"] += 1
        if st["segs_concat_ok"]:
            totals["struct_concat_ok"] += 1
        if st["no_latin"]:
            totals["struct_no_latin"] += 1
    return totals


def pct(num: int, den: int) -> str:
    if den == 0:
        return "—"
    return f"{100 * num / den:5.1f}%  ({num}/{den})"


def report(name: str, t: dict) -> None:
    print(f"\n=== {name} — {t['covered']}/{SAMPLE_SIZE} words covered ===")
    ks = t["reading_kanji_segs"]
    print(f"  READINGS   (per kanji-containing seg):")
    print(f"    correct (in JMdict)  {pct(t['reading_correct'], ks)}")
    print(f"    plausible (fugashi)  {pct(t['reading_plausible'], ks)}")
    print(f"    wrong                {pct(t['reading_wrong'], ks)}")
    print(f"    missing              {pct(t['reading_missing'], ks)}")
    print(f"    combined OK          {pct(t['reading_correct'] + t['reading_plausible'], ks)}")
    lv_total = t["level_within"] + t["level_above"] + t["level_no_kanji"]
    print(f"  LEVEL      (per sentence):")
    print(f"    within level         {pct(t['level_within'], lv_total)}")
    print(f"    above level          {pct(t['level_above'], lv_total)}")
    print(f"    no kanji in sentence {pct(t['level_no_kanji'], lv_total)}")
    print(f"  STRUCTURE  (per sentence):")
    print(f"    target word present  {pct(t['struct_has_target'], t['covered'])}")
    print(f"    segs concat matches  {pct(t['struct_concat_ok'], t['covered'])}")
    print(f"    no Latin letters     {pct(t['struct_no_latin'], t['covered'])}")
    if t["covered"]:
        avg = t["sent_len_sum"] / t["covered"]
        print(f"  avg sentence length:   {avg:.1f} chars")


def main() -> None:
    print(f"Loading Tatoeba bundle: {TATOEBA_BUNDLE}")
    tatoeba = load_tatoeba_examples()
    print(f"  {len(tatoeba)} words with examples")

    print(f"Loading LLM cache: {LLM_CACHE}")
    llm = load_llm_examples()
    print(f"  {len(llm)} words with examples")

    # Sample from words that exist in BOTH so the comparison is apples-to-apples.
    common = sorted(set(tatoeba.keys()) & set(llm.keys()))
    print(f"Words with examples in both datasets: {len(common)}")

    random.seed(SEED)
    sample = random.sample(common, min(SAMPLE_SIZE, len(common)))

    print(f"\nLoading KANJIDIC2 for level mapping: {KANJIDIC}")
    kanji = parse_kanjidic(KANJIDIC)
    kanji_jlpt = {ch: k.jlpt for ch, k in kanji.items()}

    print(f"Building JMdict reading lookup: {JMDICT}")
    jm_lookup = build_jmdict_reading_lookup(JMDICT)
    print(f"  {len(jm_lookup)} surfaces")

    t_tat = evaluate(tatoeba, sample, jm_lookup, kanji_jlpt)
    t_llm = evaluate(llm, sample, jm_lookup, kanji_jlpt)

    report("Tatoeba + fugashi (bundle v7)", t_tat)
    report("LLM-generated (cache, v8)", t_llm)

    # Side-by-side samples: pick 5 words where both datasets have entries.
    print("\n" + "=" * 72)
    print("Five side-by-side examples (random picks from the sample):")
    print("=" * 72)
    for wid in sample[:5]:
        a = tatoeba.get(wid, {})
        b = llm.get(wid, {})
        jp = a.get("jp") or b.get("jp")
        print(f"\n[{wid}]  word: {jp}")
        print(f"  Tatoeba: {a.get('sentence_jp', '—')}")
        print(f"           EN: {a.get('sentence_en', '—')}")
        print(f"           segs: {[(s.get('t'), s.get('r')) for s in (a.get('segs') or [])]}")
        print(f"  LLM:     {b.get('sentence_jp', '—')}")
        print(f"           EN: {b.get('sentence_en', '—')}")
        print(f"           segs: {[(s.get('t'), s.get('r')) for s in (b.get('segs') or [])]}")


if __name__ == "__main__":
    main()
