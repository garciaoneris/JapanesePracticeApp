"""Cross-check and repair LLM-generated segment readings against JMdict.

The 7B model used in run_llm.py gets ~70% of readings right; most of its
failures are on common words where a dictionary disagrees. This module does
two things:

1. Builds a lookup of every kanji surface form in JMdict → its allowed
   hiragana readings. For example: 意地悪 → {いじわる}, 一日 → {いちにち,
   ついたち}.

2. For each segment in a generated example:
   - If the segment surface is in JMdict:
       - Keep the LLM's reading if it's one of the valid ones (respects
         context-aware homograph choices).
       - Otherwise overwrite with the canonical first reading.
   - Else if the segment contains kanji (typically an inflected verb or an
     LLM-concatenated token like "彼女は"): fall back to fugashi to get a
     reading. Fugashi's inflection analysis is reliable — it's the compound
     tokenizer we mistrusted in the first place, not the per-token
     morphology.

Usable as a library (import `fix_segs_readings`) or as a standalone script:

    python tools/fix_readings.py                # rewrites the cache in place
    python tools/fix_readings.py --dry-run      # report changes, don't write
    python tools/fix_readings.py --out path     # write to a different file
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
from lxml import etree

if TYPE_CHECKING:
    from collections.abc import Iterable

# Force UTF-8 on Windows (same reason as run_llm.py).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


KANJI_MIN = 0x4E00
KANJI_MAX = 0x9FFF
KATAKANA_MIN = 0x30A1
KATAKANA_MAX = 0x30F6


def _is_kanji(ch: str) -> bool:
    return len(ch) == 1 and KANJI_MIN <= ord(ch) <= KANJI_MAX


def has_kanji(s: str) -> bool:
    return any(_is_kanji(c) for c in s)


def kata_to_hira(s: str) -> str:
    """Katakana → hiragana (only the main small+large block 0x30A1-0x30F6).
    Leaves chouonpu ー, iteration marks, and non-katakana untouched."""
    out: list[str] = []
    for c in s:
        cp = ord(c)
        if KATAKANA_MIN <= cp <= KATAKANA_MAX:
            out.append(chr(cp - 0x60))
        else:
            out.append(c)
    return "".join(out)


# ── JMdict surface → readings lookup ──────────────────────────────────


def build_jmdict_reading_lookup(jmdict_path: Path) -> dict[str, set[str]]:
    """Walk JMdict once, emit {kanji_form: {reading1, reading2, ...}}.

    Every k_ele (kanji form) in an entry gets mapped to EVERY r_ele
    (reading) in the same entry. That means entries with multiple readings
    (一日 → いちにち / ついたち) contribute both, and we let the LLM's
    context pick which one was meant.
    """
    parser = etree.XMLParser(resolve_entities=True, huge_tree=True)
    tree = etree.parse(str(jmdict_path), parser)
    out: dict[str, set[str]] = {}
    for entry in tree.iter("entry"):
        kebs = [k.text for k in entry.findall("k_ele/keb") if k.text]
        rebs = [r.text for r in entry.findall("r_ele/reb") if r.text]
        if not kebs or not rebs:
            continue
        for keb in kebs:
            out.setdefault(keb, set()).update(rebs)
    return out


# ── fugashi fallback for inflected / merged tokens ────────────────────

_FUGASHI_TAGGER: Any = None


def _get_fugashi_tagger() -> Any:
    """Lazy-initialize the fugashi Tagger. Loading UniDic-lite is slow (~1s)
    so we defer until a segment actually misses the JMdict lookup."""
    global _FUGASHI_TAGGER  # noqa: PLW0603
    if _FUGASHI_TAGGER is None:
        import fugashi  # noqa: PLC0415
        _FUGASHI_TAGGER = fugashi.Tagger()
    return _FUGASHI_TAGGER


def fugashi_reading(text: str) -> str | None:
    """Tokenize `text` with fugashi and return the concatenated hiragana
    reading. Returns None if any token has no reading (fugashi uses katakana
    internally; we fold to hiragana).

    We trust fugashi's per-token inflection analysis; we do NOT trust it to
    tokenize compounds correctly — but that's not what we're asking it here,
    we already have a single token from the LLM. Fugashi is free to
    sub-tokenize it if needed and we just concatenate the pieces."""
    try:
        tagger = _get_fugashi_tagger()
    except ImportError:
        return None
    parts: list[str] = []
    for tok in tagger(text):
        kana = None
        feat = getattr(tok, "feature", None)
        if feat is not None:
            # UniDic-lite exposes `kana` (surface reading) and sometimes `pron`.
            kana = getattr(feat, "kana", None) or getattr(feat, "pron", None)
        if not kana or kana == "*":
            # Pure kana tokens report their own surface as the reading —
            # fugashi also sets kana="*" for unknowns. Fall back to surface.
            if any(_is_kanji(c) for c in tok.surface):
                return None  # unknown kanji token → bail
            parts.append(tok.surface)
        else:
            parts.append(str(kana))
    return kata_to_hira("".join(parts))


def build_sentence_reading_map(sentence: str) -> list[tuple[int, int, str | None]]:
    """Tokenize the WHOLE sentence at once so fugashi's morphological analysis
    sees context. Returns [(start_char, end_char, reading_hira or None), ...]
    covering the sentence.

    Why this exists: fugashi run on "お母さん" alone sometimes picks the wrong
    reading (unidic-lite's default for isolated 母 may be はは). Run on the
    full sentence "お母さんは子供にお菓子をあげた", the tokenizer correctly
    picks お母さん → おかあさん from context. Same mechanism fixes many
    homograph cases (空→から vs そら, 行う vs 行く inflections, etc.)."""
    try:
        tagger = _get_fugashi_tagger()
    except ImportError:
        return []
    out: list[tuple[int, int, str | None]] = []
    pos = 0
    for tok in tagger(sentence):
        surface = tok.surface
        if not surface:
            continue
        # Find this surface in the original sentence starting at pos. Use
        # find() rather than tracking offsets from fugashi because some tokens
        # (e.g. normalized forms) may not align byte-for-byte.
        start = sentence.find(surface, pos)
        if start < 0:
            # Fugashi produced a token not present verbatim — skip but advance
            # pos conservatively by 1 so we don't get stuck.
            pos = min(pos + 1, len(sentence))
            continue
        end = start + len(surface)
        kana = None
        feat = getattr(tok, "feature", None)
        if feat is not None:
            kana = getattr(feat, "kana", None) or getattr(feat, "pron", None)
        if kana and kana != "*":
            reading: str | None = kata_to_hira(str(kana))
        elif not any(_is_kanji(c) for c in surface):
            reading = surface
        else:
            reading = None
        out.append((start, end, reading))
        pos = end
    return out


def reading_for_range(
    sent_map: list[tuple[int, int, str | None]],
    char_start: int,
    char_end: int,
) -> str | None:
    """Pull the concatenated reading covering [char_start, char_end) from a
    sentence reading map. Returns None if any covering token has no reading
    (unknown kanji) or the range isn't cleanly covered."""
    parts: list[str] = []
    for tstart, tend, tread in sent_map:
        if tend <= char_start:
            continue
        if tstart >= char_end:
            break
        # Token overlaps the range. Only accept a clean, full-span cover.
        if tstart < char_start or tend > char_end:
            # Token straddles the seg boundary — can't safely use
            return None
        if tread is None:
            return None
        parts.append(tread)
    return "".join(parts) if parts else None


# ── The actual fix pass ───────────────────────────────────────────────


def merge_split_compounds(
    segs: list[dict[str, Any]],
    lookup: dict[str, set[str]],
) -> int:
    """Find runs of adjacent single-kanji segs whose concatenation is a
    JMdict headword, and merge them into one seg. Fixes LLM tokenization
    errors like `{t:"今"},{t:"月"}` → `{t:"今月", r:"こんげつ"}` (which would
    otherwise render as いま+つき, the per-character kun readings).

    Uses longest-match-greedy from each position: at position i, extends
    the run as long as concatenating the next single-kanji seg still
    results in a JMdict-known compound, then merges that whole run.

    Returns the number of merges performed. Mutates `segs` in place.
    """
    def is_single_kanji_seg(s: dict[str, Any]) -> bool:
        t = s.get("t", "")
        return len(t) == 1 and bool(t) and has_kanji(t)

    merges = 0
    i = 0
    while i < len(segs):
        if not is_single_kanji_seg(segs[i]):
            i += 1
            continue
        # Find the longest run [i..end] whose concat is in JMdict.
        concat = segs[i]["t"]
        best_end = i  # inclusive; best_end == i means "no merge from here"
        j = i + 1
        while j < len(segs) and is_single_kanji_seg(segs[j]):
            concat += segs[j]["t"]
            if concat in lookup:
                best_end = j
            j += 1
        if best_end > i:
            merged_t = "".join(s["t"] for s in segs[i:best_end + 1])
            readings = lookup.get(merged_t, set())
            new_seg: dict[str, Any] = {"t": merged_t}
            if readings:
                # Prefer a reading that matches the concatenation of the
                # per-seg kanji hints if any — otherwise alphabetical first.
                new_seg["r"] = sorted(readings)[0]
            # Promote the first non-null gloss from the contributing segs.
            for s in segs[i:best_end + 1]:
                g = s.get("g")
                if g:
                    new_seg["g"] = g
                    break
            segs[i:best_end + 1] = [new_seg]
            merges += 1
            i += 1  # advance past the new merged seg
        else:
            i += 1
    return merges


def fix_segs_readings(
    segs: list[dict[str, Any]],
    lookup: dict[str, set[str]],
    *,
    word_jp: str | None = None,
    word_reading: str | None = None,
    sentence_jp: str | None = None,
) -> int:
    """Mutate `segs` in place, overwriting wrong readings. Returns the number
    of segs whose `r` field was changed.

    Preference cascade (highest-confidence signal wins):

    0. If seg.t == target word and we know the target word's canonical JMdict
       reading: use it. This is the most trustworthy signal — we PARSED it
       from JMdict's r_ele for this exact entry (e.g. 否々 → いやいや).

    1. JMdict unambiguous: the seg's surface has exactly ONE JMdict reading.
       Catches idiomatic compounds fugashi's UniDic-lite gets wrong
       (意地悪 → いじわる, not fugashi's いじあく).

    2. Sentence-context fugashi: tokenize the full sentence once, use the
       reading fugashi produces in context. Handles homographs that
       isolated-token fugashi fumbles (お母さん → おかあさん when in a
       sentence, vs おははさん when tokenized alone).

    3. Isolated-token fugashi: fall back if sentence context didn't cleanly
       cover the seg (e.g. the LLM's seg straddles a fugashi token boundary).

    4. JMdict alphabetical-first reading: last resort, better than nothing
       when we know the surface is in the dictionary but with multiple readings.

    5. Keep LLM's original reading if everything above failed.

    Also unconditionally drops `r` on pure-kana / punctuation segs (where LLM
    often stuffs a bogus gloss-as-reading).
    """
    changed = 0

    # Step 0 — fold any runs of split-apart single-kanji segs back into
    # their JMdict compound form. Must run BEFORE the per-seg reading
    # cascade so the new merged seg gets its canonical reading picked up
    # by rule 1. Each merge counts as one change.
    changed += merge_split_compounds(segs, lookup)

    # Pre-compute the sentence-level tokenization once (expensive for long
    # sentences, but we do it once per sentence — not per seg).
    sent_map: list[tuple[int, int, str | None]] = []
    if sentence_jp:
        sent_map = build_sentence_reading_map(sentence_jp)

    # Track byte offset into the sentence as we walk segs; segs concatenate to
    # reproduce sentence_jp exactly (validation guarantees this), so we can
    # just accumulate len(t).
    char_pos = 0

    for seg in segs:
        t = seg.get("t", "")
        if not t:
            continue
        current = seg.get("r")

        # Kana-only / punctuation segs: `r` is redundant at best and is often
        # a bogus synonym / garbled output from the LLM. Drop it unconditionally.
        if not has_kanji(t):
            if current is not None:
                seg.pop("r", None)
                changed += 1
            char_pos += len(t)
            continue

        new_r: str | None = None

        # Rule 0 — target word exact match.
        if word_jp and word_reading and t == word_jp:
            new_r = word_reading

        jm_readings = lookup.get(t) or set()

        # Rule 1 — JMdict unambiguous.
        if new_r is None and len(jm_readings) == 1:
            (new_r,) = jm_readings

        # Rule 2 — sentence-context fugashi.
        if new_r is None and sent_map:
            ctx = reading_for_range(sent_map, char_pos, char_pos + len(t))
            # If JMdict has readings for this surface, only accept ctx if
            # it's one of them (ctx is more trustworthy than JMdict's
            # alphabetical first, but still needs to be plausible).
            if ctx and (not jm_readings or ctx in jm_readings):
                new_r = ctx

        # Rule 3 — isolated fugashi.
        if new_r is None:
            iso = fugashi_reading(t)
            if iso and (not jm_readings or iso in jm_readings):
                new_r = iso

        # Rule 4 — JMdict alphabetical-first as last resort.
        if new_r is None and jm_readings:
            new_r = sorted(jm_readings)[0]

        # Rule 5 — nothing better than what we have; keep LLM's reading.

        char_pos += len(t)
        if new_r is None or new_r == current:
            continue
        seg["r"] = new_r
        changed += 1
    return changed


# ── Batch pass over the JSONL cache ───────────────────────────────────


CACHE_PATH = Path("tools/_data/llm_word_cache.jsonl")
JMDICT_PATH = Path("tools/_data/JMdict_e")


def _rewrite_jsonl_atomic(
    path: Path, rows: Iterable[dict[str, Any]], out_path: Path,
) -> None:
    """Write `rows` to out_path via a temp file + atomic rename. If
    out_path == path, the rewrite is in-place."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=out_path.name + ".",
        suffix=".tmp",
        dir=str(out_path.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            for row in rows:
                f.write(orjson.dumps(row))
                f.write(b"\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(out_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("rb") as f:
        for raw in f:
            if not raw.strip():
                continue
            try:
                out.append(orjson.loads(raw))
            except orjson.JSONDecodeError:
                continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--jmdict", type=Path, default=JMDICT_PATH)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write fixed cache. Default: overwrite --cache in place.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many segs would be changed, don't write.",
    )
    args = ap.parse_args()

    if not args.cache.exists():
        raise SystemExit(f"no cache at {args.cache}")
    if not args.jmdict.exists():
        raise SystemExit(f"no JMdict at {args.jmdict}")

    print(f"Loading JMdict reading lookup from {args.jmdict}…")
    lookup = build_jmdict_reading_lookup(args.jmdict)
    print(f"  {len(lookup)} surface forms")

    print(f"Loading cache from {args.cache}…")
    rows = _load_jsonl(args.cache)
    print(f"  {len(rows)} entries")

    # To drive rule 0 (target-word canonical reading) in the standalone pass,
    # we'd need each entry's JMdict word.reading. The cache doesn't store that
    # separately, but we can recover the reading for the top JMdict entry of
    # row["jp"] from the same lookup we already built: if the surface appears
    # AS a headword in JMdict, use its first reading.
    total_changes = 0
    entries_changed = 0
    for row in rows:
        segs = row.get("segs")
        if not isinstance(segs, list):
            continue
        jp = str(row.get("jp", ""))
        sentence = str(row.get("sentence_jp", ""))
        # Pick target reading from JMdict lookup if unambiguous.
        word_readings = lookup.get(jp, set())
        word_reading = next(iter(word_readings)) if len(word_readings) == 1 else None
        n = fix_segs_readings(
            segs,
            lookup,
            word_jp=jp or None,
            word_reading=word_reading,
            sentence_jp=sentence or None,
        )
        if n:
            total_changes += n
            entries_changed += 1

    print(
        f"Changed {total_changes} seg readings across {entries_changed} entries "
        f"({entries_changed / max(1, len(rows)):.0%} of entries touched)."
    )
    if args.dry_run:
        print("(dry-run — not writing)")
        return

    out_path = args.out or args.cache
    _rewrite_jsonl_atomic(args.cache, rows, out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
