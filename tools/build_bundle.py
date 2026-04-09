"""Build public/data/bundle.json from KanjiVG, KANJIDIC2, JMdict, and Tatoeba.

Run from the repo root:

    python tools/build_bundle.py --data-dir tools/_data

Expected files under --data-dir (download manually, one-time):

    kanjivg-YYYYMMDD.xml            # KanjiVG (unzipped)
    kanjidic2.xml                   # KANJIDIC2 (unzipped)
    JMdict_e                        # JMdict English-only (unzipped)
    sentences.csv                   # Tatoeba: id\tlang\ttext
    links.csv                       # Tatoeba: source_id\ttarget_id
    jlpt_n4_n5_vocab.txt            # one word per line (jp form), N5+N4 list

Sources:
    KanjiVG:   https://kanjivg.tagaini.net/
    KANJIDIC2: https://www.edrdg.org/wiki/index.php/KANJIDIC_Project
    JMdict:    https://www.edrdg.org/jmdict/j_archive.html
    Tatoeba:   https://tatoeba.org/en/downloads
    JLPT list: https://jisho.org/search tag:jlpt-n4 / n5, or the Tanos lists.

The script filters to JLPT N5+N4 kanji, pulls metadata, and emits a compact
JSON blob the PWA loads on first run.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import TYPE_CHECKING

import ahocorasick  # type: ignore[import-untyped]
import fugashi  # type: ignore[import-untyped]
import orjson
from lxml import etree  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import Iterable

_PHASE_TIMES: dict[str, float] = {}


def _timed(label: str, t_start: float) -> float:
    """Record and print elapsed time for a build phase. Returns a fresh t0."""
    dt = time.perf_counter() - t_start
    _PHASE_TIMES[label] = _PHASE_TIMES.get(label, 0.0) + dt
    print(f"  [timing] {label}: {dt:.2f}s")
    return time.perf_counter()


# Worker-process globals for the parallel fugashi segmentation pass. Each
# worker lazy-inits its own Tagger + shared lookup dicts once on startup, then
# reuses them across every task in its chunk so we don't pay per-task pickling.
_WORKER_TAGGER: "fugashi.Tagger | None" = None
_WORKER_WORD_BY_JP: "dict[str, WordOut] | None" = None
_WORKER_KANJI_MEANINGS: "dict[str, list[str]] | None" = None


def _seg_worker_init(
    word_by_jp: "dict[str, WordOut]",
    kanji_meanings: dict[str, list[str]],
) -> None:
    """Pool initializer: build one fugashi Tagger per worker process and stash
    the lookup dicts in module-level globals so _seg_worker_task can see them
    without having to re-pickle them on every task."""
    global _WORKER_TAGGER, _WORKER_WORD_BY_JP, _WORKER_KANJI_MEANINGS
    _WORKER_TAGGER = fugashi.Tagger()
    _WORKER_WORD_BY_JP = word_by_jp
    _WORKER_KANJI_MEANINGS = kanji_meanings


def _seg_worker_task(args: tuple[str, str, str]) -> tuple[str, dict[str, object]]:
    """Pool worker: segment one sentence with the per-process Tagger and
    return (word_id, example_dict) back to the parent."""
    word_id, jp_text, en_text = args
    assert _WORKER_TAGGER is not None  # set by _seg_worker_init
    segs = segment_with_furigana(
        _WORKER_TAGGER, jp_text, _WORKER_WORD_BY_JP, _WORKER_KANJI_MEANINGS
    )
    return word_id, {"jp": jp_text, "en": en_text, "segs": segs}

KANJI_RANGE = (0x4E00, 0x9FFF)


def is_kanji(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return KANJI_RANGE[0] <= cp <= KANJI_RANGE[1]


def katakana_to_hiragana(s: str) -> str:
    """Shift katakana code points down to hiragana. Chars outside the
    katakana block (U+30A1..U+30F6) pass through unchanged."""
    out: list[str] = []
    for ch in s:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            out.append(chr(cp - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def fugashi_to_category(pos1: str) -> str:
    """Map fugashi/UniDic pos1 to a JMdict-searchable category tag. Empty
    string means 'no preference — prefer noun senses, then first-listed'."""
    if pos1.startswith("名詞"):
        return "noun"
    if pos1.startswith("動詞") or pos1.startswith("助動詞"):
        return "verb"
    if pos1.startswith("形容詞"):
        return "adj-i"
    if pos1.startswith("形状詞"):
        return "adj-na"
    if pos1.startswith("副詞"):
        return "adv"
    if pos1.startswith("接続詞"):
        return "conj"
    if pos1.startswith("感動詞"):
        return "int"
    return ""


def _pos_matches(pos_str: str, category: str) -> bool:
    """Does a JMdict POS string (e.g. 'noun (common) (futsuumeishi)') match
    a high-level category like 'noun' / 'verb' / 'adj-i'?"""
    if not pos_str or not category:
        return False
    p = pos_str.lower()
    if category == "noun":
        # Exclude suffix/prefix/counter-noun senses so 人 doesn't match "noun,
        # used as a suffix" before "noun (common)".
        if "suffix" in p or "prefix" in p or "counter" in p:
            return False
        return "noun" in p
    if category == "verb":
        return "verb" in p or "godan" in p or "ichidan" in p
    if category == "adj-i":
        return "adjective (keiyoushi)" in p or p == "adjective"
    if category == "adj-na":
        return "adjectival noun" in p or "quasi-adjective" in p
    if category == "adv":
        return "adverb" in p
    if category == "conj":
        return "conjunction" in p
    if category == "int":
        return "interjection" in p
    return False


def pick_gloss(word: "WordOut", category: str) -> str | None:
    """Pick the most appropriate JMdict meaning for a token used in role
    `category`. Strategy: prefer a sense whose POS matches the requested
    category; fall back to the first noun sense (the usual dictionary-
    headword sense); fall back to meanings[0]."""
    if not word.meanings:
        return None
    if word.meaning_pos and len(word.meaning_pos) == len(word.meanings):
        if category:
            for m, p in zip(word.meanings, word.meaning_pos):
                if _pos_matches(p, category):
                    return m
        # No category match (or no category given) — prefer noun senses
        # because that's usually what a learner wants when they tap a word.
        for m, p in zip(word.meanings, word.meaning_pos):
            if _pos_matches(p, "noun"):
                return m
    return word.meanings[0]


@dataclass
class KanjiOut:
    char: str
    strokes: int
    # Modern JLPT level, 5=easiest (N5) .. 1=hardest (N1). 0 means "no JLPT
    # level assigned but this kanji is in the jouyou or jinmeiyou set".
    jlpt: int
    # KANJIDIC2 grade: 1-6 = kyouiku (elementary), 8 = general jouyou,
    # 9-10 = jinmeiyou, 0 = unknown. Used as a secondary sort key.
    grade: int = 0
    on: list[str] = field(default_factory=list)
    kun: list[str] = field(default_factory=list)
    meanings: list[str] = field(default_factory=list)
    svg: str = ""
    words: list[str] = field(default_factory=list)
    # A handful of {word, reading, meaning, example sentence} triples the app
    # picks from at random during the practice morph animation.
    callouts: list[dict[str, str]] = field(default_factory=list)


@dataclass
class WordOut:
    id: str
    jp: str
    reading: str
    meanings: list[str] = field(default_factory=list)
    # Parallel to `meanings`: meaning_pos[i] is the primary POS tag of the
    # JMdict sense that produced meanings[i]. Enables POS-aware sense picking
    # so a noun-context token gets the noun sense (e.g., 人 → "person", not
    # "-ian (e.g. Italian)" which is the suffix sense).
    meaning_pos: list[str] = field(default_factory=list)
    pos: list[str] = field(default_factory=list)
    kanji: list[str] = field(default_factory=list)
    # Each example: {"en": str, "jp": str, "segs": list[{"t": str, "r": str | None, "g": str | None}]}
    examples: list[dict[str, object]] = field(default_factory=list)


def segment_with_furigana(
    tagger: "fugashi.Tagger",
    sentence: str,
    word_by_jp: dict[str, "WordOut"] | None = None,
    kanji_meanings: dict[str, list[str]] | None = None,
) -> list[dict[str, str]]:
    """Split a Japanese sentence into segments using fugashi + UniDic-lite.

    Each segment is a dict with:
      - t: surface text (the token from fugashi). Always present.
      - r: hiragana reading. OPTIONAL — only emitted for kanji segments that
           have a non-trivial reading. Pure-kana segments omit it entirely to
           keep the bundle small.
      - g: English gloss. OPTIONAL — only emitted for kanji segments where
           JMdict or the per-char fallback produced something.

    Dropping the keys when there's nothing to store (instead of setting them
    to `null`) shaves a few megabytes off the final bundle because every
    segment otherwise carried `"r":null,"g":null`.
    """
    out: list[dict[str, str]] = []
    for tok in tagger(sentence):
        surface: str = tok.surface
        if not surface:
            continue
        has_kanji = any(is_kanji(c) for c in surface)

        # Reading: katakana → hiragana, surface-aligned. Only for kanji segs
        # since pure-kana segments don't need furigana.
        reading: str | None = None
        if has_kanji:
            kana = getattr(tok.feature, "kana", "") or ""
            if kana:
                hira = katakana_to_hiragana(kana)
                if hira and hira != surface:
                    reading = hira

        # Dictionary form for JMdict fallback lookup. `orthBase` is the clean
        # surface form of the lemma (e.g., 私, 食べる). `lemma` sometimes has
        # trailing POS disambiguators like "私-代名詞" so we prefer orthBase.
        dict_form = getattr(tok.feature, "orthBase", "") or surface

        # Part of speech → JMdict category for sense-aware gloss picking.
        pos1 = getattr(tok.feature, "pos1", "") or ""
        category = fugashi_to_category(pos1)

        gloss: str | None = None
        if has_kanji:
            if word_by_jp is not None:
                w = word_by_jp.get(surface) or word_by_jp.get(dict_form)
                if w is not None:
                    picked = pick_gloss(w, category)
                    if picked:
                        gloss = picked if len(picked) <= 60 else picked[:57] + "…"
            if gloss is None and kanji_meanings is not None:
                parts: list[str] = []
                for c in surface:
                    if is_kanji(c):
                        ms = kanji_meanings.get(c)
                        if ms:
                            parts.append(ms[0])
                if parts:
                    g2 = " / ".join(parts)
                    gloss = g2 if len(g2) <= 60 else g2[:57] + "…"

        seg: dict[str, str] = {"t": surface}
        if reading:
            seg["r"] = reading
        if gloss:
            seg["g"] = gloss
        out.append(seg)
    return out


def parse_kanjidic(path: Path) -> dict[str, KanjiOut]:
    """Parse every kanji from KANJIDIC2 that has EITHER a JLPT level OR a
    school grade (jouyou 1-8, jinmeiyou 9-10). That's ~2500 kanji covering
    the entire JLPT curriculum plus all daily-use kanji. Kanji without any
    tag are skipped — they're too obscure for a learner-facing app.

    The `jlpt` field stored on each KanjiOut is the MODERN N5-N1 scale
    (5=easiest, 1=hardest) mapped from KANJIDIC2's pre-2010 levels, or 0
    for "no JLPT level — shown as plain jouyou in the UI".

    Old JLPT 4 → modern N5
    Old JLPT 3 → modern N4
    Old JLPT 2 → modern N3 if grade 1-4 (elementary school, ~310 kanji)
                 modern N2 if grade 5-8 (late elementary + jouyou, ~429 kanji)
                 The pre-2010 level 2 covered both modern N3 and N2; splitting
                 by school grade gives a reasonable educational progression.
    Old JLPT 1 → modern N1
    """
    print(f"Parsing KANJIDIC2: {path}")
    tree = etree.parse(str(path))
    out: dict[str, KanjiOut] = {}
    for ch_el in tree.iter("character"):
        literal = ch_el.findtext("literal") or ""
        if not is_kanji(literal):
            continue
        misc = ch_el.find("misc")
        if misc is None:
            continue

        jlpt_el = misc.find("jlpt")
        jlpt_old: int | None = None
        if jlpt_el is not None and jlpt_el.text:
            try:
                jlpt_old = int(jlpt_el.text)
            except ValueError:
                pass

        grade_el = misc.find("grade")
        grade: int | None = None
        if grade_el is not None and grade_el.text:
            try:
                grade = int(grade_el.text)
            except ValueError:
                pass

        # Keep if the kanji is curriculum-worthy: JLPT-tagged or jouyou/jinmei.
        if jlpt_old is None and grade is None:
            continue

        strokes_el = misc.find("stroke_count")
        strokes = int(strokes_el.text) if strokes_el is not None and strokes_el.text else 0

        # Old JLPT 2 spans both modern N3 and N2. We split using school
        # grade: kanji taught in grades 1-4 (early elementary) map to N3,
        # grades 5-8 (late elementary / general jouyou) map to N2.
        if jlpt_old == 2:
            modern_jlpt = 3 if (grade or 99) <= 4 else 2
        else:
            modern_jlpt = {4: 5, 3: 4, 1: 1}.get(jlpt_old or -1, 0)

        on: list[str] = []
        kun: list[str] = []
        meanings: list[str] = []
        for rm in ch_el.iter("reading_meaning"):
            group = rm.find("rmgroup")
            if group is None:
                continue
            for r in group.findall("reading"):
                rtype = r.get("r_type")
                if rtype == "ja_on" and r.text:
                    on.append(r.text)
                elif rtype == "ja_kun" and r.text:
                    kun.append(r.text)
            for m in group.findall("meaning"):
                if m.get("m_lang") is None and m.text:
                    meanings.append(m.text)

        out[literal] = KanjiOut(
            char=literal,
            strokes=strokes,
            jlpt=modern_jlpt,
            grade=grade or 0,
            on=on,
            kun=kun,
            meanings=meanings,
        )

    # Per-level counts for the build log.
    by_level: dict[int, int] = {}
    for k in out.values():
        by_level[k.jlpt] = by_level.get(k.jlpt, 0) + 1
    level_str = ", ".join(f"N{lv}={n}" if lv else f"un={n}" for lv, n in sorted(by_level.items(), reverse=True))
    print(f"  kept {len(out)} kanji ({level_str})")
    return out


def parse_kanjivg(path: Path, chars: set[str]) -> dict[str, str]:
    print(f"Parsing KanjiVG: {path}")
    parser = etree.XMLParser(resolve_entities=False, huge_tree=True)
    tree = etree.parse(str(path), parser)
    out: dict[str, str] = {}

    for k in tree.iter("kanji"):
        kid = k.get("id", "")
        m = re.match(r"kvg:kanji_([0-9a-fA-F]+)", kid)
        if not m:
            continue
        ch = chr(int(m.group(1), 16))
        if ch not in chars:
            continue

        # Collect every <path> in document order. KanjiVG paths are not in a namespace.
        paths = [p.get("d", "") for p in k.iter("path")]
        if not paths:
            continue

        # Wrap the paths in a <g> with hoisted stroke presentation attributes.
        # A <g> (not the root <svg>) because the frontend appends <circle> +
        # <text> stroke-number markers at runtime, and those must NOT inherit
        # fill="none" or stroke-width="3" from the SVG root. Using <g> keeps
        # the inheritance scoped to the actual kanji strokes.
        svg_paths = "".join(f'<path d="{d}"/>' for d in paths if d)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 109 109">'
            '<g stroke="currentColor" fill="none" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round">{svg_paths}</g></svg>'
        )
        out[ch] = svg

    print(f"  got stroke SVG for {len(out)} kanji")
    return out


POS_KEEP_PREFIXES = ("n", "v", "adj", "adv", "exp", "prt", "int", "conj", "pn")
# JMdict priority tags that mark a headword as "common". Keeping any of these filters
# the ~200k JMdict entries down to ~30k high-frequency words.
COMMON_PRIO_TAGS = {"ichi1", "ichi2", "news1", "news2", "spec1", "spec2", "gai1"}


def parse_jmdict(path: Path, allowed_kanji: set[str], vocab_whitelist: set[str]) -> dict[str, WordOut]:
    print(f"Parsing JMdict: {path}")
    parser = etree.XMLParser(resolve_entities=True, huge_tree=True)
    tree = etree.parse(str(path), parser)
    out: dict[str, WordOut] = {}

    for entry in tree.iter("entry"):
        ent_seq = entry.findtext("ent_seq") or ""
        # Pick the most common written form.
        k_ele = entry.find("k_ele")
        r_ele = entry.find("r_ele")
        keb = k_ele.findtext("keb") if k_ele is not None else None
        reb = r_ele.findtext("reb") if r_ele is not None else ""
        jp = keb or reb or ""
        if not jp:
            continue

        # Priority check: keep only common words (unless the whitelist says otherwise).
        prio_tags: set[str] = set()
        if k_ele is not None:
            prio_tags.update(p.text for p in k_ele.findall("ke_pri") if p.text)
        if r_ele is not None:
            prio_tags.update(p.text for p in r_ele.findall("re_pri") if p.text)
        is_common = bool(prio_tags & COMMON_PRIO_TAGS)

        if vocab_whitelist:
            if jp not in vocab_whitelist and reb not in vocab_whitelist:
                continue
        elif not is_common:
            continue

        # Every kanji in jp must be in our allowed set.
        jp_kanji = [c for c in jp if is_kanji(c)]
        if jp_kanji and any(c not in allowed_kanji for c in jp_kanji):
            continue

        meanings: list[str] = []
        meaning_pos: list[str] = []
        pos: set[str] = set()
        for sense in entry.findall("sense"):
            sense_pos: list[str] = []
            for p in sense.findall("pos"):
                if p.text:
                    sense_pos.append(p.text)
                    pos.add(p.text)
            primary_sense_pos = sense_pos[0] if sense_pos else ""
            for g in sense.findall("gloss"):
                if g.get("{http://www.w3.org/XML/1998/namespace}lang") in (None, "eng") and g.text:
                    meanings.append(g.text)
                    # Keep meanings and meaning_pos in lock-step.
                    meaning_pos.append(primary_sense_pos)

        if not meanings:
            continue

        # Filter POS to the useful prefixes.
        pos_list = sorted(p for p in pos if any(p.startswith(prefix) for prefix in POS_KEEP_PREFIXES))

        out[ent_seq] = WordOut(
            id=ent_seq,
            jp=jp,
            reading=reb,
            meanings=meanings[:4],
            meaning_pos=meaning_pos[:4],
            pos=pos_list,
            kanji=sorted(set(jp_kanji)),
        )
    print(f"  kept {len(out)} words")
    return out


def _load_lang_sentences(path: Path) -> dict[int, str]:
    """Load a Tatoeba per-language sentences file.

    Supports both the per-language format (id\\ttext) and the full export
    (id\\tlang\\ttext) by indexing the last column.
    """
    out: dict[int, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                sid = int(parts[0])
            except ValueError:
                continue
            out[sid] = parts[-1]
    return out


def attach_tatoeba(
    words: dict[str, WordOut],
    jp_sent_path: Path,
    en_sent_path: Path,
    links_path: Path,
    word_by_jp: dict[str, WordOut],
    kanji_meanings: dict[str, list[str]],
    *,
    kanji_jlpt: dict[str, int] | None = None,
    include_word_ids: "set[str] | None" = None,
    per_word: int = 1,
    max_len: int = 40,
) -> None:
    if not all(p.exists() for p in (jp_sent_path, en_sent_path, links_path)):
        print("Tatoeba files missing, skipping example sentences.")
        return

    print(f"Parsing Tatoeba: {jp_sent_path.name}, {en_sent_path.name}, {links_path.name}")
    t0 = time.perf_counter()
    jp_sents = _load_lang_sentences(jp_sent_path)
    en_sents = _load_lang_sentences(en_sent_path)
    print(f"  jp sentences: {len(jp_sents)}, en sentences: {len(en_sents)}")

    # links file: jpn_id\teng_id (per-language link file is already pre-filtered).
    jp_to_en: dict[int, int] = {}
    with links_path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                a, b = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if a not in jp_to_en and a in jp_sents and b in en_sents:
                jp_to_en[a] = b
    print(f"  jpn->eng links: {len(jp_to_en)}")
    t0 = _timed("tatoeba_load", t0)

    # Only consider jp sentences that have a short length and an English translation.
    candidates = [
        (sid, jp_sents[sid])
        for sid in jp_to_en
        if len(jp_sents[sid]) <= max_len
    ]

    # Sort candidates so simpler sentences come first. The Aho–Corasick sweep
    # takes the *first* match per word, so sorting by complexity means each
    # word naturally gets the easiest available example. "Complexity" = number
    # of kanji in the sentence whose JLPT level is below N3 (i.e., N2/N1 or
    # ungraded). Fewer rare kanji → more readable for an early learner.
    if kanji_jlpt:
        _kj = kanji_jlpt  # local alias for the lambda closure

        def _complexity(pair: tuple[int, str]) -> tuple[int, int]:
            text = pair[1]
            rare = sum(1 for c in text if is_kanji(c) and _kj.get(c, 0) < 3)
            return (rare, len(text))

        candidates.sort(key=_complexity)

    # Build an Aho–Corasick automaton over every vocab surface form. This
    # turns the first pass from O(candidates × vocab) substring checks into a
    # single O(text) sweep per candidate sentence, which is ~30–100× faster
    # on the 29k-word / 50k-sentence scale we hit after the kanji expansion.
    #
    # include_word_ids lets the caller restrict which words are eligible for
    # examples at all — we skip rare-kanji-only words to shrink the bundle.
    if include_word_ids is not None:
        vocab_forms: dict[str, WordOut] = {
            w.jp: w
            for w in words.values()
            if w.jp and w.id in include_word_ids
        }
    else:
        vocab_forms = {w.jp: w for w in words.values() if w.jp}
    automaton = ahocorasick.Automaton()
    for form in vocab_forms:
        automaton.add_word(form, form)
    automaton.make_automaton()

    # First pass: pick raw sentences (no segmentation yet — that's expensive).
    picked: dict[str, list[tuple[str, str]]] = {}
    for sid, jp_text in candidates:
        # The automaton returns one hit per occurrence, so dedupe forms that
        # appear multiple times in the same sentence (the old loop checked
        # each form at most once per sentence).
        seen_here: set[str] = set()
        for _end, form in automaton.iter(jp_text):
            if form in seen_here:
                continue
            seen_here.add(form)
            word = vocab_forms[form]
            if len(picked.get(word.id, [])) >= per_word:
                continue
            picked.setdefault(word.id, []).append((jp_text, en_sents[jp_to_en[sid]]))
    t0 = _timed("tatoeba_substring_match", t0)

    # Second pass: segment with fugashi/UniDic only the sentences we're
    # keeping. Each per-sentence tagger call is ~1–5 ms; on this machine
    # (12 cores) parallelizing across a Pool gives ~7× on the segmentation
    # phase even after paying ~1–2 s per-worker UniDic warmup.
    tasks: list[tuple[str, str, str]] = [
        (word_id, jp_text, en_text)
        for word_id, pairs in picked.items()
        for jp_text, en_text in pairs
    ]
    total_examples = 0

    if len(tasks) < 500:
        # Small workloads: skip the pool overhead entirely.
        print("  segmenting examples with fugashi + UniDic (single-process)…")
        tagger = fugashi.Tagger()
        for word_id, jp_text, en_text in tasks:
            segs = segment_with_furigana(tagger, jp_text, word_by_jp, kanji_meanings)
            words[word_id].examples.append({"jp": jp_text, "en": en_text, "segs": segs})
            total_examples += 1
    else:
        n_workers = max(1, (os.cpu_count() or 2) - 1)
        print(
            f"  segmenting examples with fugashi + UniDic "
            f"({n_workers}-worker pool over {len(tasks)} examples)…"
        )
        with Pool(
            processes=n_workers,
            initializer=_seg_worker_init,
            initargs=(word_by_jp, kanji_meanings),
        ) as pool:
            for word_id, example in pool.imap_unordered(
                _seg_worker_task, tasks, chunksize=64
            ):
                words[word_id].examples.append(example)
                total_examples += 1

    attached = sum(1 for w in words.values() if w.examples)
    print(f"  attached {total_examples} examples to {attached}/{len(words)} words")
    _timed("tatoeba_segment", t0)


def build(data_dir: Path, out_path: Path, *, validate: bool) -> None:
    kanjidic_path = data_dir / "kanjidic2.xml"
    kanjivg_path = next(data_dir.glob("kanjivg-*.xml"), None) or data_dir / "kanjivg.xml"
    jmdict_path = data_dir / "JMdict_e"
    # Tatoeba per-language files (what the downloader grabs in the README).
    jpn_sent_path = data_dir / "jpn_sentences.tsv"
    eng_sent_path = data_dir / "eng_sentences.tsv"
    links_path = data_dir / "jpn_eng_links.tsv"
    whitelist_path = data_dir / "jlpt_n4_n5_vocab.txt"

    for p in (kanjidic_path, kanjivg_path, jmdict_path):
        if not p.exists():
            raise SystemExit(f"missing required file: {p}")

    vocab_whitelist: set[str] = set()
    if whitelist_path.exists():
        vocab_whitelist = {line.strip() for line in whitelist_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        print(f"Loaded vocab whitelist: {len(vocab_whitelist)} entries")
    else:
        print("No vocab whitelist found; filtering JMdict by priority tags (ichi1/news1/spec1/gai1)")

    t_build0 = time.perf_counter()
    kanji = parse_kanjidic(kanjidic_path)
    t_build0 = _timed("parse_kanjidic", t_build0)
    svgs = parse_kanjivg(kanjivg_path, set(kanji.keys()))
    for ch, k in kanji.items():
        k.svg = svgs.get(ch, "")
    t_build0 = _timed("parse_kanjivg", t_build0)

    allowed_kanji = set(kanji.keys())
    words = parse_jmdict(jmdict_path, allowed_kanji, vocab_whitelist)
    t_build0 = _timed("parse_jmdict", t_build0)

    # Index words by their Japanese surface form so the example segmenter can
    # look up glosses quickly. JMdict sometimes has TWO entries sharing a
    # headword — e.g. 人 has a separate entry for the suffix "-ian / -ite /
    # -er" and another for the noun "person". If we naively take the first
    # one we see, the suffix entry wins and the learner gets "-ian" as the
    # gloss for bare 人. Prefer entries whose senses include at least one
    # noun POS over ones that only list suffix / counter / prefix senses.
    def _has_noun_sense(w: WordOut) -> bool:
        return any(_pos_matches(p, "noun") for p in w.meaning_pos)

    word_by_jp: dict[str, WordOut] = {}
    for w in words.values():
        existing = word_by_jp.get(w.jp)
        if existing is None:
            word_by_jp[w.jp] = w
            continue
        # Upgrade from a noun-less entry to a noun-bearing one.
        if _has_noun_sense(w) and not _has_noun_sense(existing):
            word_by_jp[w.jp] = w

    # Per-char KANJIDIC2 meanings for fallback glosses when a segment's surface
    # form isn't in JMdict. Covers every kanji we know about, not just N5/N4.
    kanji_meanings: dict[str, list[str]] = {ch: k.meanings for ch, k in kanji.items()}

    # Pick which words are eligible to get Tatoeba example sentences attached.
    # With the full curriculum kanji set the unfiltered bundle is ~38 MB,
    # blowing past the 15 MB service-worker precache cap. To fit we skip
    # examples for words that contain ANY N1 or ungraded kanji — i.e. we
    # only give examples to words a learner at N2-or-easier can *fully*
    # read. Kana-only words are always included so common particles and
    # interjections still carry examples.
    #
    # modern jlpt: 5=N5 (easiest) .. 1=N1 (hardest), 0=ungraded.
    CORE_JLPT_THRESHOLD = 2  # every kanji in the word must be N2 or easier
    include_word_ids: set[str] = set()
    for wid, w in words.items():
        word_kanji_levels = [kanji[c].jlpt for c in w.kanji if c in kanji]
        if not word_kanji_levels:
            include_word_ids.add(wid)  # kana-only — always eligible
            continue
        if all(lv >= CORE_JLPT_THRESHOLD for lv in word_kanji_levels):
            include_word_ids.add(wid)
    print(
        f"  {len(include_word_ids)}/{len(words)} words eligible for examples "
        f"(all kanji N2 or easier, or kana-only)"
    )
    t_build0 = _timed("build_word_indexes", t_build0)

    attach_tatoeba(
        words,
        jpn_sent_path,
        eng_sent_path,
        links_path,
        word_by_jp,
        kanji_meanings,
        kanji_jlpt={ch: k.jlpt for ch, k in kanji.items()},
        include_word_ids=include_word_ids,
    )
    t_build0 = time.perf_counter()  # attach_tatoeba prints its own sub-phases

    # Back-link words to kanji.
    for w in words.values():
        for ch in w.kanji:
            if ch in kanji:
                kanji[ch].words.append(w.id)

    # Build up to 4 "callouts" per kanji — (word, reading, meaning, sentence)
    # triples used by the practice-morph UI. We prefer words that contain the
    # kanji AND have at least one Tatoeba example, and we try to pick words with
    # different readings so a learner hears more than one pronunciation.
    for ch, k in kanji.items():
        seen_readings: set[str] = set()
        picked: list[dict[str, str]] = []
        # First pass: diversify by reading.
        for w_id in k.words:
            if len(picked) >= 4:
                break
            w = words.get(w_id)
            if w is None or not w.examples or not w.reading:
                continue
            if w.reading in seen_readings:
                continue
            seen_readings.add(w.reading)
            ex = w.examples[0]
            picked.append({
                "wordJp": w.jp,
                "wordReading": w.reading,
                "wordMeaning": pick_gloss(w, "") or "",
                "exJp": str(ex.get("jp", "")),
                "exEn": str(ex.get("en", "")),
            })
        # Second pass: fill in with any remaining words if we still have slots.
        if len(picked) < 4:
            for w_id in k.words:
                if len(picked) >= 4:
                    break
                w = words.get(w_id)
                if w is None or not w.examples or not w.reading:
                    continue
                if any(p["wordJp"] == w.jp for p in picked):
                    continue
                ex = w.examples[0]
                picked.append({
                    "wordJp": w.jp,
                    "wordReading": w.reading,
                    "wordMeaning": pick_gloss(w, "") or "",
                    "exJp": str(ex.get("jp", "")),
                    "exEn": str(ex.get("en", "")),
                })
        k.callouts = picked

    t_build0 = _timed("callouts_and_backlinks", t_build0)

    if validate:
        missing_svg = [ch for ch, k in kanji.items() if not k.svg]
        if missing_svg:
            print(f"WARNING: {len(missing_svg)} kanji missing SVG: {''.join(missing_svg[:20])}…")
        print(f"counts: kanji={len(kanji)} words={len(words)} examples={sum(len(w.examples) for w in words.values())}")

    # Build the runtime dicts explicitly so we can drop build-time-only
    # fields like `meaning_pos` (used by the Python POS-aware sense picker
    # but never read by the Svelte app). Bumped to "7" because the
    # curriculum expansion from ~284 to ~2900 kanji means every cached
    # client needs to refetch.
    bundle_obj: dict[str, object] = {
        "version": "7",
        "kanji": {
            ch: {
                "char": k.char,
                "strokes": k.strokes,
                "jlpt": k.jlpt,
                "grade": k.grade,
                "on": k.on,
                "kun": k.kun,
                "meanings": k.meanings,
                "svg": k.svg,
                "words": k.words,
                "callouts": k.callouts,
            }
            for ch, k in kanji.items()
        },
        "words": {
            wid: {
                "id": w.id,
                "jp": w.jp,
                "reading": w.reading,
                "meanings": w.meanings,
                # meaning_pos and pos are intentionally omitted — meaning_pos
                # is build-time only, pos was ~1.4 MB of Vocab-card display
                # text that we can live without.
                "kanji": w.kanji,
                # examples keep segs + en but drop jp because segs.map(t)
                # exactly reconstructs it; the frontend has an exampleJp()
                # helper for the call sites that need a joined string.
                "examples": [
                    {"en": ex["en"], "segs": ex["segs"]}
                    for ex in w.examples
                ],
            }
            for wid, w in words.items()
        },
    }
    t_build0 = _timed("build_bundle_dict", t_build0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = orjson.dumps(bundle_obj)
    out_path.write_bytes(out_bytes)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.2f} MB)")
    _timed("serialize_json", t_build0)

    # Totals
    total = sum(_PHASE_TIMES.values())
    print(f"\n=== phase totals ({total:.1f}s) ===")
    for k, v in sorted(_PHASE_TIMES.items(), key=lambda kv: -kv[1]):
        print(f"  {k:32} {v:7.2f}s  ({100 * v / total:5.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("tools/_data"))
    ap.add_argument("--out", type=Path, default=Path("public/data/bundle.json"))
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    build(args.data_dir, args.out, validate=args.validate)


if __name__ == "__main__":
    main()
