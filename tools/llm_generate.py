"""LLM-backed generation of per-word example sentences.

Talks to either a local vLLM server (OpenAI-compatible endpoint, preferred) or
an Ollama server (fallback for smoke-testing). For each JMdict word, asks the
model to produce ONE natural example sentence that:

1. Contains the target word verbatim.
2. Uses ONLY kanji at the word's level or lower (level = max of its kanji's
   Lvl 1..5, where Lvl 1 = old N5, Lvl 5 = ungraded). Anything else has to be
   hiragana, katakana, or punctuation.
3. Ships together with the per-segment tokenization (surface text, hiragana
   reading on kanji tokens, 1-3 word English gloss on content words).

Because the sentence, its reading, and the gloss all come out of the same
JSON object, the runtime furigana can't disagree with the Japanese text. That
fixes the class of reading errors UniDic-lite produces on compound words
(e.g. 意地悪女 getting split as 意地 + 悪女 instead of 意地悪 + 女).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Mapping

# ── Pydantic schema the model must emit ───────────────────────────────

KANJI_MIN = 0x4E00
KANJI_MAX = 0x9FFF


def is_kanji(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return KANJI_MIN <= cp <= KANJI_MAX


class Seg(BaseModel):
    """One segment of a tokenized Japanese sentence, same shape as the
    app's runtime `Segment` type (src/lib/data/types.ts)."""

    t: str
    r: str | None = None  # hiragana reading; null for pure-kana / punctuation
    g: str | None = None  # English gloss; null for particles / punctuation


class WordExample(BaseModel):
    """The full payload for one word."""

    sentence_jp: str
    sentence_en: str
    segs: list[Seg]


# ── Prompt templates ──────────────────────────────────────────────────

SYSTEM_PROMPT = """Write ONE short natural Japanese example sentence for the target word, for JLPT learners.
Output ONE JSON object matching the schema. Nothing else — no markdown, no prose.

THE #1 RULE: sentence_jp contains ZERO Latin letters (a-z, A-Z). If you can't express a word in Japanese, pick a simpler sentence — NEVER substitute an English word like "wise", "ink", "stop", "ila", "beautiful". Zero tolerance.

Rules (any violation = invalid):

A. sentence_jp:
   - MUST contain the target word verbatim.
   - Only hiragana/katakana/kanji/ 。、？！ — NO Latin letters, NO Simplified Chinese (use 試 not 试, 間 not 间, 経 not 经, 書 not 书).
   - Only kanji listed in allowed_kanji (+ target's kanji) may appear. Other words → hiragana.
   - Grammatical and idiomatic, under 25 chars. Avoid stuffing the word into awkward templates like "彼は〈word〉が重要です".

B. segs (this is the tricky rule):
   - Concatenating every seg.t must reproduce sentence_jp exactly.
   - Each trailing 。、？！ is its own final seg.
   - Inflected verbs/adjectives stay as ONE seg: {"t":"美しい","r":"うつくしい"} — NOT split as 美 / しい. Same for 着ています, 読んでいる, 食べました.
   - Established compounds stay as ONE seg: {"t":"交通費","r":"こうつうひ"} — NOT split as 交通 / 費. Same for 間一髪→かんいっぱつ.
   - Honorific お / ご prefix stays attached to its word as ONE seg: {"t":"お化け","r":"おばけ"}, {"t":"お子様","r":"おこさま"}, {"t":"ご挨拶","r":"ごあいさつ"} — NOT split as お / 化け.
   - Plural suffix 〜ら / 〜たち stays attached: {"t":"彼ら","r":"かれら"} — NOT split as 彼 / ら.

C. r (reading) per seg:
   - If t has any kanji: r = pure hiragana reading of the whole token. Never katakana, never romaji, never a synonym.
   - If t is pure kana / punctuation: r = null.

D. g (gloss) per seg:
   - Plain English, 1-3 words, only on content words (nouns, verbs, adjectives).
   - Never Japanese, never romaji, never "~ish" style suffix markers, never grammar labels like "past tense".
   - Particles / copulas / auxiliaries / punctuation: g = null.

Correct example for word=本 (ほん, book):
{"sentence_jp":"この本は面白いです。","sentence_en":"This book is interesting.","segs":[{"t":"この","r":null,"g":null},{"t":"本","r":"ほん","g":"book"},{"t":"は","r":null,"g":null},{"t":"面白い","r":"おもしろい","g":"interesting"},{"t":"です","r":null,"g":null},{"t":"。","r":null,"g":null}]}"""


USER_TEMPLATE = """word: {jp}
reading: {reading}
meaning: {meaning}
{allowed_line}
Return ONLY the JSON object."""

# When allowed_kanji would exceed this many characters, the set is effectively
# unrestricted so we drop the list from the prompt and use a placeholder —
# saves ~1000+ tokens per request. Set below Lvl 3's ~1023 kanji because the
# stronger prompt has grown and otherwise we bust the 2048 context window.
# Lvl 3+ words rely on the validation retry loop to catch disallowed kanji.
ALLOWED_KANJI_INLINE_LIMIT = 500


def render_user_prompt(
    jp: str,
    reading: str,
    meaning: str,
    allowed_kanji: str,
    previous_error: str | None = None,
) -> str:
    """Build the user message. On retry, prepend a note about the prior
    validation failure so the model self-corrects."""
    if len(allowed_kanji) > ALLOWED_KANJI_INLINE_LIMIT:
        allowed_line = "allowed_kanji: (any common Japanese kanji)"
    elif allowed_kanji:
        allowed_line = f"allowed_kanji: {allowed_kanji}"
    else:
        allowed_line = "allowed_kanji: (use kana only, no kanji permitted)"
    base = USER_TEMPLATE.format(
        jp=jp,
        reading=reading,
        meaning=meaning,
        allowed_line=allowed_line,
    )
    if previous_error:
        return (
            f"Your previous answer was rejected: {previous_error}\n"
            f"Try again, fixing the violation.\n\n{base}"
        )
    return base


# ── Backends ──────────────────────────────────────────────────────────

VLLM_URL = "http://127.0.0.1:8000/v1/chat/completions"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# Hand-written schema for the OpenAI-standard `response_format.json_schema`
# strict mode. vLLM v0.19+ enforces this through xgrammar.
#
# Strict mode requires (a) every property listed in `required`, (b)
# `additionalProperties: false` on every object. Pydantic's auto-generated
# schema puts nullables in `anyOf` with defaults, which strict mode rejects —
# so we hand-write it to stay under the constraints.
WORD_EXAMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sentence_jp": {"type": "string"},
        "sentence_en": {"type": "string"},
        "segs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "t": {"type": "string"},
                    "r": {"type": ["string", "null"]},
                    "g": {"type": ["string", "null"]},
                },
                "required": ["t", "r", "g"],
            },
        },
    },
    "required": ["sentence_jp", "sentence_en", "segs"],
}


async def call_vllm(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    json_schema: dict[str, Any],  # kept for signature compat; we use the hand-written schema  # noqa: ARG001
) -> str:
    """Call the vLLM OpenAI-compatible endpoint with hard-constrained JSON
    output via response_format.json_schema (strict). Returns the raw JSON
    string in message.content."""
    resp = await client.post(
        VLLM_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.15,
            "max_tokens": 250,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "WordExample",
                    "strict": True,
                    "schema": WORD_EXAMPLE_SCHEMA,
                },
            },
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    return str(payload["choices"][0]["message"]["content"])


async def call_ollama(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    json_schema: dict[str, Any],
) -> str:
    """Call a local Ollama daemon. Newer Ollama versions accept a JSON schema
    via the `format` field; older versions take the string "json" — we pass the
    schema because it's strictly better when supported and ignored otherwise."""
    resp = await client.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": json_schema,
            "options": {"temperature": 0.3},
        },
        timeout=180,
    )
    resp.raise_for_status()
    payload = resp.json()
    return str(payload["message"]["content"])


# ── Validation ────────────────────────────────────────────────────────

KATAKANA_MIN = 0x30A1
KATAKANA_MAX = 0x30F6

# Trailing sentence-final punctuation the model often drops from segs.
TRAILING_PUNCT = "。、？！?!"


def normalize_width(s: str) -> str:
    """Fold fullwidth ASCII to halfwidth so "ＣＤ" compares equal to "CD".
    Leaves CJK and kana unchanged."""
    out: list[str] = []
    for ch in s:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            out.append(chr(cp - 0xFEE0))
        elif ch == "\u3000":  # fullwidth space
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def validate_example(
    ex: WordExample,
    allowed_kanji: set[str],
    word_jp: str,
) -> str | None:
    """Check the model's output against the constraints. Returns None if
    valid, else a short error string suitable for the retry prompt.

    Also *repairs* two common model glitches in-place on `ex`:
      - segs missing the trailing 。 / 、 / ? / ! → append it as a new seg
      - fullwidth ASCII in the target word missing from sentence → retry in
        normalized form
    """
    # 0. Sentence must not contain ASCII letters. The model sometimes falls
    #    back to English when it can't express a concept in Japanese
    #    ("はwiseです", "お世辞を ila した"). Force a retry with explicit
    #    feedback rather than let the garbage through.
    ascii_letters = [c for c in ex.sentence_jp if c.isascii() and c.isalpha()]
    if ascii_letters and not (
        # Allow if the target word itself has ASCII letters (a few JMdict
        # entries like "Ｔバック" resolve to halfwidth "Tバック" after our
        # normalization). Rare; check explicitly.
        any(c.isascii() and c.isalpha() for c in word_jp)
    ):
        return (
            f"sentence_jp must not contain Latin letters, found: "
            f"{''.join(sorted(set(ascii_letters)))}"
        )

    # 1. Target word must appear in the sentence. Accept fullwidth↔halfwidth
    #    equivalence (JMdict has "ＣＤプレーヤー" but models emit "CDプレーヤー").
    if word_jp not in ex.sentence_jp:
        if normalize_width(word_jp) not in normalize_width(ex.sentence_jp):
            return f"sentence_jp must contain the word {word_jp!r}"
        # Normalize the sentence to use the form the word expects so downstream
        # segs/kanji checks line up — rewrite into the original fullwidth form.
        ex.sentence_jp = ex.sentence_jp.replace(
            normalize_width(word_jp), word_jp
        )

    # 2. Segs must concatenate to the sentence exactly. Auto-heal the common
    #    case where the model omits the final 。 — append it as its own seg
    #    rather than bouncing the retry. Also tolerate fullwidth↔halfwidth
    #    ASCII differences between segs and sentence (model often normalizes
    #    Ｔバック → Tバック in segs even when the sentence kept fullwidth).
    concat = "".join(s.t for s in ex.segs)
    if concat != ex.sentence_jp:
        # Try the width-normalized comparison first.
        if normalize_width(concat) == normalize_width(ex.sentence_jp):
            # Rewrite the sentence to match the segs so downstream kanji checks
            # operate on the exact same characters the segs will render.
            ex.sentence_jp = concat
        elif (
            ex.sentence_jp.startswith(concat)
            and ex.sentence_jp[len(concat):] in TRAILING_PUNCT
        ):
            ex.segs.append(Seg(t=ex.sentence_jp[len(concat):]))
            concat = ex.sentence_jp
        elif (
            normalize_width(ex.sentence_jp).startswith(normalize_width(concat))
            and ex.sentence_jp[len(concat):] in TRAILING_PUNCT
        ):
            # Width + trailing punctuation, both glitches at once.
            tail = ex.sentence_jp[len(concat):]
            ex.segs.append(Seg(t=tail))
            ex.sentence_jp = concat + tail
        else:
            return (
                "concatenating segs.t must equal sentence_jp "
                f"(got {concat!r} vs {ex.sentence_jp!r})"
            )

    # 3. Every kanji in the sentence must be in the allowed set.
    bad = sorted({c for c in ex.sentence_jp if is_kanji(c) and c not in allowed_kanji})
    if bad:
        return f"disallowed kanji in sentence: {''.join(bad)}"

    # 4. Every kanji-containing seg needs a hiragana reading.
    for s in ex.segs:
        if any(is_kanji(c) for c in s.t):
            if not s.r:
                return f"seg {s.t!r} contains kanji but has no reading"
            # Reading must be hiragana only (no katakana, no kanji, no latin).
            for c in s.r:
                cp = ord(c)
                if KATAKANA_MIN <= cp <= KATAKANA_MAX:
                    return f"reading {s.r!r} for seg {s.t!r} contains katakana"
                if is_kanji(c):
                    return f"reading {s.r!r} for seg {s.t!r} contains kanji"
                if c.isascii() and c.isalpha():
                    return f"reading {s.r!r} for seg {s.t!r} contains latin letters"

    return None


# ── End-to-end generate-one-word ──────────────────────────────────────

MAX_ATTEMPTS = 3


async def generate_word_example(
    client: httpx.AsyncClient,
    backend: str,
    model: str,
    word_jp: str,
    reading: str,
    meaning: str,
    allowed_kanji: set[str],
) -> tuple[WordExample, list[str]]:
    """Drive the LLM to produce one valid WordExample for a word.

    Returns (example, errors_attempted) where errors_attempted lists each
    failed attempt's validation error for diagnostics.

    Raises RuntimeError if MAX_ATTEMPTS fails — the caller decides whether
    to skip the word or abort the run.
    """
    schema = WordExample.model_json_schema()
    allowed_str = "".join(sorted(allowed_kanji))
    previous_error: str | None = None
    errors: list[str] = []

    for _ in range(MAX_ATTEMPTS):
        user = render_user_prompt(
            jp=word_jp,
            reading=reading,
            meaning=meaning,
            allowed_kanji=allowed_str,
            previous_error=previous_error,
        )
        try:
            if backend == "vllm":
                raw = await call_vllm(client, model, SYSTEM_PROMPT, user, schema)
            else:
                raw = await call_ollama(client, model, SYSTEM_PROMPT, user, schema)
            ex = WordExample.model_validate_json(raw)
        except Exception as exc:  # network / JSON / schema error
            previous_error = f"response could not be parsed: {exc}"
            errors.append(previous_error)
            continue

        err = validate_example(ex, allowed_kanji, word_jp)
        if err is None:
            return ex, errors
        previous_error = err
        errors.append(err)

    raise RuntimeError(
        f"LLM failed to produce a valid example for {word_jp!r} after "
        f"{MAX_ATTEMPTS} attempts; last error: {previous_error}"
    )


# ── Level-aware allowed-kanji helper ──────────────────────────────────

# Mirrors the LEVEL_JLPT map in src/routes/Home.svelte.
# Modern JLPT scale stored on each kanji: 5=N5 (easiest) .. 1=N1, 0=ungraded.
# Level 1 = N5, 2 = N4, 3 = N3+N2 merged, 4 = N1, 5 = ungraded.
LEVEL_OF_JLPT: dict[int, int] = {5: 1, 4: 2, 3: 3, 2: 3, 1: 4, 0: 5}


def level_of_kanji(kanji_char: str, kanji_index: Mapping[str, Any]) -> int:
    """Return the curriculum level (1-5) of a single kanji. Unknown kanji
    default to 5 (treat as "hardest") so they're never falsely included."""
    k = kanji_index.get(kanji_char)
    if k is None:
        return 5
    jlpt = getattr(k, "jlpt", None) if not isinstance(k, dict) else k.get("jlpt")
    if jlpt is None:
        return 5
    return LEVEL_OF_JLPT.get(int(jlpt), 5)


def word_level(kanji_chars: list[str], kanji_index: Mapping[str, Any]) -> int:
    """A word's level is the max level of any kanji in it. Kana-only
    words default to Lvl 5 (no kanji restriction) — they have no intrinsic
    level signal and a kana-only adverb like あっさり would otherwise force
    a ridiculous N5-only example sentence."""
    if not kanji_chars:
        return 5
    return max(level_of_kanji(c, kanji_index) for c in kanji_chars)


def allowed_kanji_for_word(
    word_kanji: list[str],
    kanji_index: Mapping[str, Any],
) -> set[str]:
    """Return the set of kanji permitted in an example sentence for a word
    at level N: every kanji in the bundle whose level is <= N."""
    level_cap = word_level(word_kanji, kanji_index)
    return {
        ch
        for ch, k in kanji_index.items()
        if level_of_kanji(ch, {ch: k}) <= level_cap
    }
