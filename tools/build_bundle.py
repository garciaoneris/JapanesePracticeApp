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
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]
from pykakasi import kakasi  # type: ignore[import-untyped]

KANJI_RANGE = (0x4E00, 0x9FFF)


def is_kanji(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return KANJI_RANGE[0] <= cp <= KANJI_RANGE[1]


@dataclass
class KanjiOut:
    char: str
    strokes: int
    jlpt: int
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
    pos: list[str] = field(default_factory=list)
    kanji: list[str] = field(default_factory=list)
    # Each example: {"en": str, "jp": str, "segs": list[{"t": str, "r": str | None}]}
    # `r` is set only on segments whose `t` contains kanji NOT in the target set,
    # so the UI can render furigana exactly where the learner needs it.
    examples: list[dict[str, object]] = field(default_factory=list)


def segment_with_furigana(
    kks: object,
    sentence: str,
    word_by_jp: dict[str, "WordOut"] | None = None,
    kanji_meanings: dict[str, list[str]] | None = None,
) -> list[dict[str, str | None]]:
    """Split a Japanese sentence into segments.

    Each segment carries:
      - t: surface text (the chunk from pykakasi).
      - r: hiragana reading — populated on *every* kanji-containing segment,
           so the runtime UI can decide per-user whether to render furigana
           (based on which kanji the learner has mastered).
      - g: English gloss, populated on every kanji-containing segment. Tries
           JMdict first (first English meaning for the exact surface form);
           falls back to a concatenation of per-kanji KANJIDIC2 meanings
           when the surface form isn't in JMdict, so every kanji is tappable.
    """
    out: list[dict[str, str | None]] = []
    for piece in kks.convert(sentence):  # type: ignore[attr-defined]
        text = piece.get("orig", "")
        if not text:
            continue
        has_kanji = any(is_kanji(c) for c in text)

        # Reading: always store on kanji segments so the runtime can pick.
        reading: str | None = None
        if has_kanji:
            hira = piece.get("hira", "")
            if hira and hira != text:
                reading = hira

        # Gloss: JMdict surface-form match wins. If no match, synthesize a
        # per-char fallback from KANJIDIC2 meanings joined with " / ".
        gloss: str | None = None
        if has_kanji:
            if word_by_jp is not None:
                w = word_by_jp.get(text)
                if w is not None and w.meanings:
                    g = w.meanings[0]
                    gloss = g if len(g) <= 60 else g[:57] + "…"
            if gloss is None and kanji_meanings is not None:
                parts: list[str] = []
                for c in text:
                    if is_kanji(c):
                        ms = kanji_meanings.get(c)
                        if ms:
                            parts.append(ms[0])
                if parts:
                    g2 = " / ".join(parts)
                    gloss = g2 if len(g2) <= 60 else g2[:57] + "…"

        seg: dict[str, str | None] = {
            "t": text,
            "r": reading,
            "g": gloss,
        }
        out.append(seg)
    return out


def parse_kanjidic(path: Path, jlpt_levels: set[int]) -> dict[str, KanjiOut]:
    print(f"Parsing KANJIDIC2: {path}")
    tree = etree.parse(str(path))
    out: dict[str, KanjiOut] = {}
    for ch_el in tree.iter("character"):
        literal = ch_el.findtext("literal") or ""
        if not is_kanji(literal):
            continue
        misc = ch_el.find("misc")
        jlpt_el = misc.find("jlpt") if misc is not None else None
        if jlpt_el is None or jlpt_el.text is None:
            continue
        try:
            jlpt = int(jlpt_el.text)
        except ValueError:
            continue
        if jlpt not in jlpt_levels:
            continue
        strokes_el = misc.find("stroke_count") if misc is not None else None
        strokes = int(strokes_el.text) if strokes_el is not None and strokes_el.text else 0

        # Map pre-2010 JLPT levels (1-4) to modern levels (N5 easiest, N1 hardest):
        #   old 4 -> modern 5 (N5)
        #   old 3 -> modern 4 (N4)
        # This is a lossy approximation but matches the UI labels the app uses.
        modern_jlpt = {4: 5, 3: 4}.get(jlpt, jlpt)

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

        out[literal] = KanjiOut(char=literal, strokes=strokes, jlpt=modern_jlpt, on=on, kun=kun, meanings=meanings)
    print(f"  kept {len(out)} kanji at JLPT {sorted(jlpt_levels)}")
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

        svg_paths = "\n".join(
            f'<path d="{d}" stroke="currentColor" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
            for d in paths
            if d
        )
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 109 109">{svg_paths}</svg>'
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
        pos: set[str] = set()
        for sense in entry.findall("sense"):
            for p in sense.findall("pos"):
                if p.text:
                    pos.add(p.text)
            for g in sense.findall("gloss"):
                if g.get("{http://www.w3.org/XML/1998/namespace}lang") in (None, "eng") and g.text:
                    meanings.append(g.text)

        if not meanings:
            continue

        # Filter POS to the useful prefixes.
        pos_list = sorted(p for p in pos if any(p.startswith(prefix) for prefix in POS_KEEP_PREFIXES))

        out[ent_seq] = WordOut(
            id=ent_seq,
            jp=jp,
            reading=reb,
            meanings=meanings[:4],
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
    per_word: int = 2,
    max_len: int = 40,
) -> None:
    if not all(p.exists() for p in (jp_sent_path, en_sent_path, links_path)):
        print("Tatoeba files missing, skipping example sentences.")
        return

    print(f"Parsing Tatoeba: {jp_sent_path.name}, {en_sent_path.name}, {links_path.name}")
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

    # Only consider jp sentences that have a short length and an English translation.
    candidates = [
        (sid, jp_sents[sid])
        for sid in jp_to_en
        if len(jp_sents[sid]) <= max_len
    ]

    # Build inverted index: for every word-form in our vocab, the list of sentence IDs that contain it.
    # This is O(sentences × vocab) but the substring check is cheap.
    vocab_forms = {w.jp: w for w in words.values()}
    vocab_list = list(vocab_forms.items())

    # First pass: pick raw sentences (no segmentation yet — that's expensive).
    picked: dict[str, list[tuple[str, str]]] = {}
    for sid, jp_text in candidates:
        for form, word in vocab_list:
            if word.id in picked and len(picked[word.id]) >= per_word:
                continue
            if form in jp_text:
                picked.setdefault(word.id, []).append((jp_text, en_sents[jp_to_en[sid]]))

    # Second pass: segment with pykakasi only the sentences we're keeping.
    print("  segmenting examples with pykakasi…")
    kks = kakasi()
    attached = 0
    total_examples = 0
    for word_id, pairs in picked.items():
        word = words[word_id]
        for jp_text, en_text in pairs:
            segs = segment_with_furigana(kks, jp_text, word_by_jp, kanji_meanings)
            word.examples.append({"jp": jp_text, "en": en_text, "segs": segs})
            total_examples += 1
        if word.examples:
            attached += 1
    print(f"  attached {total_examples} examples to {attached}/{len(words)} words")


def build(data_dir: Path, out_path: Path, *, validate: bool) -> None:
    # KANJIDIC2 uses the PRE-2010 4-level JLPT scale (1=hardest, 4=easiest).
    # Modern N5 ~ old level 4; modern N5+N4 ~ old levels 4 + 3.
    jlpt_levels = {3, 4}

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

    kanji = parse_kanjidic(kanjidic_path, jlpt_levels)
    svgs = parse_kanjivg(kanjivg_path, set(kanji.keys()))
    for ch, k in kanji.items():
        k.svg = svgs.get(ch, "")

    allowed_kanji = set(kanji.keys())
    words = parse_jmdict(jmdict_path, allowed_kanji, vocab_whitelist)

    # Index words by their Japanese surface form so the example segmenter can
    # look up glosses for content-words quickly.
    word_by_jp: dict[str, WordOut] = {}
    for w in words.values():
        # Don't overwrite an earlier (more common) word if there's a collision.
        word_by_jp.setdefault(w.jp, w)

    # Per-char KANJIDIC2 meanings for fallback glosses when a segment's surface
    # form isn't in JMdict. Covers every kanji we know about, not just N5/N4.
    kanji_meanings: dict[str, list[str]] = {ch: k.meanings for ch, k in kanji.items()}

    attach_tatoeba(words, jpn_sent_path, eng_sent_path, links_path, word_by_jp, kanji_meanings)

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
                "wordMeaning": w.meanings[0] if w.meanings else "",
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
                    "wordMeaning": w.meanings[0] if w.meanings else "",
                    "exJp": str(ex.get("jp", "")),
                    "exEn": str(ex.get("en", "")),
                })
        k.callouts = picked

    if validate:
        missing_svg = [ch for ch, k in kanji.items() if not k.svg]
        if missing_svg:
            print(f"WARNING: {len(missing_svg)} kanji missing SVG: {''.join(missing_svg[:20])}…")
        print(f"counts: kanji={len(kanji)} words={len(words)} examples={sum(len(w.examples) for w in words.values())}")

    bundle = {
        # Bump whenever the schema changes — the PWA loader compares this against
        # whatever it stored in IndexedDB and refetches on mismatch.
        "version": "5",
        "kanji": {ch: asdict(k) for ch, k in kanji.items()},
        "words": {wid: asdict(w) for wid, w in words.items()},
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({size_mb:.2f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("tools/_data"))
    ap.add_argument("--out", type=Path, default=Path("public/data/bundle.json"))
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    build(args.data_dir, args.out, validate=args.validate)


if __name__ == "__main__":
    main()
