<script lang="ts">
  import { link, push } from 'svelte-spa-router';
  import { onMount, onDestroy } from 'svelte';
  import { bundle } from '../lib/data/bundle';
  import { dueSrs, putSrs, getSrs, getAllBestScores, getMeta, putMeta } from '../lib/data/db';
  import { grade, newCard } from '../lib/srs/sm2';
  import { speakJa } from '../lib/speech/tts';
  import { KNOWN_THRESHOLD } from '../lib/data/known';
  import { reviewScoreKey, reviewDrawScoreKey } from '../lib/data/mode';
  import type { Grade, SrsState } from '../lib/data/types';
  import { recordMistake } from '../lib/data/mistakes';
  import PracticeMorph from '../lib/ui/PracticeMorph.svelte';
  import RevealKanji from '../lib/ui/RevealKanji.svelte';
  import Petal from '../lib/ui/Petal.svelte';
  import Blossom from '../lib/ui/Blossom.svelte';
  import { addXp, getXpState } from '../lib/gamification/xp';
  import { addMinutes, startTick, stopTick } from '../lib/gamification/goal';
  import { onGoalHit, getStreakState } from '../lib/gamification/streak';
  import { newlyEarnedFromEvent, earn, type BadgeDef } from '../lib/gamification/badges';

  const NEW_PER_SESSION = 10;

  let queue = $state<SrsState[]>([]);
  let idx = $state(0);
  let done = $state(false);
  let reviewResults = $state<Map<string, { correct: number; total: number }>>(new Map());

  /** Session counters drive the microcopy strip and the Complete summary. */
  let sessionCorrect = $state(0);
  let sessionBestStreak = $state(0);
  let correctStreak = $state(0);
  let sessionStartTs = Date.now();
  let sessionStartLevel = 1;
  let sessionStartXp = 0;

  const LEVEL_JLPT: Record<number, number[]> = { 1: [5], 2: [4], 3: [3, 2], 4: [1], 5: [0] };

  function getLevelFilter(): number | null {
    const v = sessionStorage.getItem('home-jlpt-filter');
    if (!v || v === 'all') return null;
    const n = Number(v);
    return [1, 2, 3, 4, 5].includes(n) ? n : null;
  }

  let levelFilter = $state<number | null>(null);
  const levelLabel = $derived(levelFilter !== null ? `Lvl ${levelFilter}` : '');

  function cardMatchesFilter(card: SrsState, b: ReturnType<typeof bundle>, level: number): boolean {
    const jlpts = LEVEL_JLPT[level] ?? [];
    if (card.kind === 'kanji') {
      const ch = card.id.replace('kanji:', '');
      const k = b.kanji[ch];
      return k ? jlpts.includes(k.jlpt) : false;
    }
    const wid = card.id.replace('word:', '');
    const w = b.words[wid];
    if (!w) return false;
    return w.kanji.some((ch) => jlpts.includes(b.kanji[ch]?.jlpt ?? -1));
  }

  async function buildQueue() {
    const now = Date.now();
    const b = bundle();
    levelFilter = getLevelFilter();

    let due = await dueSrs(now, 200);
    const native = (await getMeta<boolean>('native-mode')) === true;
    const scores = await getAllBestScores();

    due = due.filter((c) => {
      if (levelFilter !== null && !cardMatchesFilter(c, b, levelFilter!)) return false;
      if (native) return true;
      if (c.kind === 'kanji') {
        const ch = c.id.slice('kanji:'.length);
        return (scores.get(ch) ?? 0) >= KNOWN_THRESHOLD;
      }
      const wid = c.id.slice('word:'.length);
      const w = b.words[wid];
      if (!w) return false;
      return w.kanji.length === 0 || w.kanji.every((ch) => (scores.get(ch) ?? 0) >= KNOWN_THRESHOLD);
    });

    if (due.length < NEW_PER_SESSION) {
      const need = NEW_PER_SESSION - due.length;
      const newCandidates: SrsState[] = [];
      for (const k of Object.values(b.kanji)) {
        if (newCandidates.length >= need) break;
        if (!native && (scores.get(k.char) ?? 0) < KNOWN_THRESHOLD) continue;
        if (levelFilter !== null && !LEVEL_JLPT[levelFilter]?.includes(k.jlpt)) continue;
        const id = `kanji:${k.char}`;
        if (!(await getSrs(id))) newCandidates.push(newCard(id, 'kanji', now));
      }
      for (const w of Object.values(b.words)) {
        if (newCandidates.length >= need) break;
        if (!native && w.kanji.length > 0 && !w.kanji.every((c) => (scores.get(c) ?? 0) >= KNOWN_THRESHOLD)) continue;
        if (levelFilter !== null && !w.kanji.some((ch) => LEVEL_JLPT[levelFilter!]?.includes(b.kanji[ch]?.jlpt ?? -1))) continue;
        const id = `word:${w.id}`;
        if (!(await getSrs(id))) newCandidates.push(newCard(id, 'word', now));
      }
      for (const c of newCandidates) await putSrs(c);
      due.push(...newCandidates);
    }

    for (let i = due.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [due[i], due[j]] = [due[j], due[i]];
    }
    queue = due;
    idx = 0;
    done = queue.length === 0;
    sessionStartTs = Date.now();
    const startXp = await getXpState();
    sessionStartLevel = startXp.level;
    sessionStartXp = startXp.xp;
  }

  onMount(() => {
    buildQueue();
    startTick();
  });
  onDestroy(() => stopTick());

  const current = $derived(queue[idx]);
  const display = $derived.by(() => {
    if (!current) return null;
    const b = bundle();
    if (current.kind === 'kanji') {
      const key = current.id.slice('kanji:'.length);
      return { kind: 'kanji' as const, kanji: b.kanji[key] };
    } else {
      const key = current.id.slice('word:'.length);
      return { kind: 'word' as const, word: b.words[key] };
    }
  });

  // ── Multiple-choice quiz ──────────────────────────────────────────
  let choices = $state<string[]>([]);
  let correctChoice = $state('');
  let picked = $state<number | null>(null);
  let drawScoreDone = $state<number | null>(null);

  function cardDisplayMode(card: SrsState | undefined): 'choice' | 'draw' {
    if (!card || card.kind !== 'kanji') return 'choice';
    let h = 0;
    for (const c of card.id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return h % 2 === 0 ? 'draw' : 'choice';
  }
  const cardMode = $derived(cardDisplayMode(current));

  function shuffle<T>(arr: T[]): T[] {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function buildChoices() {
    if (!display) return;
    const b = bundle();
    let correct: string;
    if (display.kind === 'kanji' && display.kanji) {
      correct = display.kanji.meanings.slice(0, 2).join(', ');
    } else if (display.kind === 'word' && display.word) {
      correct = display.word.meanings[0] ?? '';
    } else {
      return;
    }
    correctChoice = correct;
    const pool: string[] = [];
    for (const k of Object.values(b.kanji)) {
      const m = k.meanings.slice(0, 2).join(', ');
      if (m && m !== correct) pool.push(m);
    }
    const distractors = shuffle(pool).slice(0, 3);
    choices = shuffle([correct, ...distractors]);
    picked = null;
  }

  $effect(() => {
    if (display && cardMode === 'choice') buildChoices();
  });

  function trackResult(ch: string, isCorrect: boolean): void {
    const prev = reviewResults.get(ch) ?? { correct: 0, total: 0 };
    reviewResults.set(ch, {
      correct: prev.correct + (isCorrect ? 1 : 0),
      total: prev.total + 1,
    });
    if (isCorrect) {
      sessionCorrect += 1;
      correctStreak += 1;
      if (correctStreak > sessionBestStreak) sessionBestStreak = correctStreak;
    } else {
      correctStreak = 0;
    }
  }

  async function pickChoice(i: number) {
    if (picked !== null) return;
    picked = i;
    const isCorrect = choices[i] === correctChoice;
    if (!current) return;
    const g: Grade = isCorrect ? 'good' : 'again';
    const next = grade(current, g);
    await putSrs(next);

    const ch = current.kind === 'kanji'
      ? current.id.replace('kanji:', '')
      : current.id.replace('word:', '').charAt(0);
    trackResult(ch, isCorrect);

    if (!isCorrect) {
      if (current.kind === 'kanji') {
        recordMistake({ type: 'kanji-meaning', id: current.id.replace('kanji:', '') }).catch(() => {});
      } else {
        recordMistake({ type: 'word-meaning', id: current.id.replace('word:', '') }).catch(() => {});
      }
    }

    // XP: +8 for correct (per spec 'good' grade), +2 effort credit for wrong.
    addXp(isCorrect ? 8 : 2).catch(() => {});

    if (display) {
      if (display.kind === 'kanji' && display.kanji) {
        const r = display.kanji.kun[0] ?? display.kanji.on[0] ?? display.kanji.char;
        speakJa(r);
      } else if (display.kind === 'word' && display.word) {
        speakJa(display.word.jp);
      }
    }
  }

  async function onDrawScore(score: number) {
    if (!current || drawScoreDone !== null) return;
    drawScoreDone = score;
    const isCorrect = score >= 70;
    const g: Grade = isCorrect ? 'good' : 'again';
    const next = grade(current, g);
    await putSrs(next);

    const ch = current.id.replace('kanji:', '');
    trackResult(ch, isCorrect);

    const rdKey = await reviewDrawScoreKey();
    const existing = (await getMeta<Record<string, number>>(rdKey)) ?? {};
    existing[ch] = Math.max(existing[ch] ?? 0, score);
    await putMeta(rdKey, existing);

    if (!isCorrect) {
      recordMistake({ type: 'kanji-writing', id: ch }).catch(() => {});
    }

    // XP: drawing success is harder than choice — grant a bit more.
    addXp(isCorrect ? 12 : 2).catch(() => {});

    if (display && display.kind === 'kanji' && display.kanji) {
      const r = display.kanji.kun[0] ?? display.kanji.on[0] ?? display.kanji.char;
      speakJa(r);
    }
  }

  async function finishSession(): Promise<void> {
    done = true;

    // Persist per-kanji review percentages (keep best).
    const rsKey = await reviewScoreKey();
    const existing = (await getMeta<Record<string, number>>(rsKey)) ?? {};
    for (const [ch, r] of reviewResults) {
      const pct = Math.round((r.correct / r.total) * 100);
      existing[ch] = Math.max(existing[ch] ?? 0, pct);
    }
    await putMeta(rsKey, existing);

    // Bonus XP for completing the session + any daily-goal hit.
    const { state: goalAfter, justHitGoal } = await addMinutes(
      (Date.now() - sessionStartTs) / 60_000,
    );
    if (justHitGoal) {
      await addXp(50).catch(() => {});
      await onGoalHit().catch(() => {});
    }

    // Badge checks — award any new ones before navigating to /complete.
    const streakState = await getStreakState();
    const candidates = newlyEarnedFromEvent({
      sessionReviews: queue.length,
      sessionBestStreak,
      streakDays: streakState.streakDays,
    });
    const earned: BadgeDef[] = [];
    for (const id of candidates) {
      const def = await earn(id);
      if (def) earned.push(def);
    }

    // XP delta + level-up detection — pull final state once, diff against start.
    const endXp = await getXpState();
    const levelUp = endXp.level > sessionStartLevel
      ? { from: sessionStartLevel, to: endXp.level }
      : null;

    sessionStorage.setItem(
      'review-session-summary',
      JSON.stringify({
        reviews: queue.length,
        correct: sessionCorrect,
        bestStreak: sessionBestStreak,
        durationSec: Math.round((Date.now() - sessionStartTs) / 1000),
        xpGained: endXp.xp - sessionStartXp,
        levelUp,
        justHitGoal,
        goalMinutes: goalAfter.goalMinutes,
        streakDays: streakState.streakDays,
        earnedBadges: earned.map((b) => ({ id: b.id, title: b.title, criteria: b.criteria })),
      }),
    );
    push('/complete');
  }

  async function advance() {
    if (idx + 1 >= queue.length) {
      await finishSession();
    } else {
      idx += 1;
      picked = null;
      drawScoreDone = null;
    }
  }

  // ── UI derivations ────────────────────────────────────────────────
  const progress = $derived(queue.length === 0 ? 0 : (idx + (picked !== null || drawScoreDone !== null ? 1 : 0)));
  const encourageLine = $derived.by(() => {
    if (correctStreak >= 7) return { bold: "On fire!", rest: `${correctStreak} in a row. Stay with the rhythm — don't rush.` };
    if (correctStreak >= 4) return { bold: "Nice rhythm.", rest: `${correctStreak} in a row. Keep it going.` };
    if (correctStreak >= 1) return { bold: 'Good.', rest: 'Next one when you are ready.' };
    return { bold: 'Fresh card.', rest: 'Take a breath and read it.' };
  });
</script>

<div class="screen">
  <!-- ── Topbar ──────────────────────────────────────── -->
  <header class="topbar">
    <a class="exit" href="/" use:link aria-label="Exit review">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </a>
    <div class="topbar-right">
      {#if levelLabel}
        <span class="pill pill-accent">{levelLabel}</span>
      {/if}
      {#if queue.length > 0}
        <span class="pill pill-mint tnum">◆ {sessionCorrect} correct</span>
        <span class="pill pill-muted tnum">{Math.min(queue.length, progress + 1)} of {queue.length}</span>
      {/if}
    </div>
  </header>

  <!-- ── Progress track ─────────────────────────────── -->
  {#if queue.length > 0}
    <div class="track" aria-label="Session progress">
      {#each queue as _, i (i)}
        <div class="track-seg" class:filled={i < progress}></div>
      {/each}
    </div>
  {/if}

  {#if done}
    <div class="center">
      <h2>All done for now!</h2>
      <p class="muted">Reviewed {queue.length} card{queue.length === 1 ? '' : 's'}.</p>
      <button class="primary" onclick={buildQueue}>Another round</button>
    </div>
  {:else if !current || !display}
    <div class="center muted">Loading…</div>
  {:else if cardMode === 'draw' && display.kind === 'kanji' && display.kanji}
    <!-- ── DRAW MODE ─────────────────────────────────── -->
    <section class="review-card">
      <div class="card-bloom" aria-hidden="true"><Blossom size={180} /></div>
      <div class="card-inner">
        <div class="prompt-pill-row">
          <span class="pill pill-accent">Draw this kanji</span>
        </div>
        <div class="draw-meaning">{display.kanji.meanings.slice(0, 3).join(' · ')}</div>
        <div class="peek">
          {#key current.id + '-peek'}
            <RevealKanji svg={display.kanji.svg} strokeCount={Math.min(3, display.kanji.strokes)} />
          {/key}
          <span class="peek-hint">max 3 peeks</span>
        </div>
      </div>
    </section>

    <section class="canvas-wrap">
      {#key current.id + '-morph'}
        <PracticeMorph
          kanji={display.kanji}
          minimal={true}
          hideRefOnMount={true}
          onScore={onDrawScore}
        />
      {/key}
    </section>

    {#if drawScoreDone !== null}
      <div class="answer-reveal">
        <div class="reveal-reading jp-sans">
          {display.kanji.on.join('、') || '—'} · {display.kanji.kun.map((r) => r.replace(/[.\-]/g, '')).join('、') || '—'}
        </div>
        <div class="reveal-meaning">{display.kanji.meanings.join(', ')}</div>
        <div class="draw-score-line tnum" class:ok={drawScoreDone >= 70} class:bad={drawScoreDone < 70}>
          Score: {drawScoreDone} / 100 · {drawScoreDone >= 70 ? 'passed ✓' : 'try again ✗'}
        </div>
      </div>
      <div class="single-action">
        <button class="primary" onclick={advance}>
          {idx + 1 >= queue.length ? 'Finish' : 'Next →'}
        </button>
      </div>
    {/if}
  {:else}
    <!-- ── CHOICE MODE ───────────────────────────────── -->
    <section class="review-card">
      <div class="card-bloom" aria-hidden="true"><Blossom size={180} /></div>
      <div class="card-inner">
        <div class="prompt-pill-row">
          <span class="pill pill-accent">Read this kanji</span>
        </div>
        {#if display.kind === 'kanji' && display.kanji}
          <div class="big-glyph jp-serif">{display.kanji.char}</div>
        {:else if display.kind === 'word' && display.word}
          <div class="big-word jp-serif">{display.word.jp}</div>
          <div class="word-reading-hint jp-sans">{display.word.reading}</div>
        {/if}
        {#if picked !== null}
          <div class="answer-reveal">
            {#if display.kind === 'kanji' && display.kanji}
              <div class="reveal-reading jp-sans">
                {display.kanji.kun.map((r) => r.replace(/[.\-]/g, '')).join('、') || display.kanji.on.join('、')}
              </div>
              <div class="reveal-meaning">
                {display.kanji.meanings.join(', ')}
                {#if display.kanji.on.length > 0}<span class="secondary"> · {display.kanji.on.join('、')}</span>{/if}
              </div>
            {:else if display.kind === 'word' && display.word}
              <div class="reveal-reading jp-sans">{display.word.reading}</div>
              <div class="reveal-meaning">{display.word.meanings.join('; ')}</div>
            {/if}
          </div>
        {/if}
      </div>
    </section>

    <div class="choices">
      {#each choices as choice, i}
        <button
          class="choice-btn"
          class:correct={picked !== null && choice === correctChoice}
          class:wrong={picked !== null && i === picked && choice !== correctChoice}
          class:dimmed={picked !== null && choice !== correctChoice && i !== picked}
          disabled={picked !== null}
          onclick={() => pickChoice(i)}
        >
          {choice}
        </button>
      {/each}
    </div>

    {#if picked !== null}
      <div class="single-action">
        <button class="primary" onclick={advance}>
          {idx + 1 >= queue.length ? 'Finish' : 'Next →'}
        </button>
      </div>
    {/if}
  {/if}

  {#if !done && queue.length > 0}
    <div class="encourage">
      <span class="encourage-icon" aria-hidden="true"><Petal size={14} /></span>
      <span><b>{encourageLine.bold}</b> {encourageLine.rest}</span>
    </div>
  {/if}

  {#if !done && display}
    <div class="jump">
      {#if display.kind === 'kanji' && display.kanji}
        <a href={`/learn/${encodeURIComponent(display.kanji.char)}`} use:link>Open lesson →</a>
      {:else if display.kind === 'word' && display.word}
        <a href={`/vocab/${encodeURIComponent(display.word.id)}`} use:link>Open card →</a>
      {/if}
    </div>
  {/if}
</div>

<style>
  .screen {
    max-width: 720px;
    margin: 0 auto;
    padding: 16px 16px 40px;
  }

  /* ── Topbar ─────────────────────────────────────────────── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .exit {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink-2);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
  }
  .topbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }

  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.02em;
  }
  .pill-accent { background: var(--accent-soft); color: var(--accent); }
  .pill-mint { background: var(--mint); color: white; }
  .pill-muted { background: var(--surface-2); color: var(--ink-2); }

  /* ── Progress track ─────────────────────────────────────── */
  .track {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
  }
  .track-seg {
    flex: 1;
    height: 6px;
    border-radius: 999px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    transition: background 0.3s ease;
  }
  .track-seg.filled {
    background: var(--gradient-brand);
    border-color: transparent;
  }

  /* ── Review card ────────────────────────────────────────── */
  .review-card {
    border-radius: 28px;
    background: var(--surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-md);
    padding: 24px;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
  }
  .card-bloom {
    position: absolute;
    right: -30px;
    top: -30px;
    color: var(--accent-2);
    opacity: 0.08;
    pointer-events: none;
  }
  .card-inner { position: relative; z-index: 1; }
  .prompt-pill-row {
    display: flex;
    justify-content: center;
    margin-bottom: 10px;
  }
  .big-glyph {
    font-size: 160px;
    text-align: center;
    color: var(--ink);
    line-height: 1;
    margin: 10px 0 16px;
    letter-spacing: -0.02em;
  }
  .big-word {
    font-size: 72px;
    text-align: center;
    color: var(--ink);
    line-height: 1;
    margin: 10px 0 4px;
  }
  .word-reading-hint {
    text-align: center;
    color: var(--accent);
    font-size: 20px;
    margin-bottom: 16px;
  }
  .draw-meaning {
    font-size: 22px;
    text-align: center;
    color: var(--ink);
    font-weight: 800;
    line-height: 1.2;
    margin: 8px 0 14px;
  }
  .peek {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .peek-hint {
    color: var(--muted);
    font-size: 11px;
    letter-spacing: 0.03em;
  }

  .answer-reveal {
    text-align: center;
    margin-top: 16px;
    padding: 12px 14px;
    border-radius: 14px;
    background: var(--surface-2);
    border: 1px solid var(--border);
  }
  .reveal-reading {
    font-size: 22px;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 4px;
  }
  .reveal-meaning {
    font-size: 14px;
    color: var(--ink-2);
  }
  .reveal-meaning .secondary { color: var(--muted); }
  .draw-score-line {
    font-size: 13px;
    margin-top: 6px;
    font-weight: 700;
  }
  .draw-score-line.ok { color: var(--mint); }
  .draw-score-line.bad { color: var(--rose); }

  /* Canvas wrap for draw-mode */
  .canvas-wrap {
    border-radius: 22px;
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 16px;
    box-shadow: var(--shadow-sm);
    margin-bottom: 12px;
  }

  /* ── Choices ────────────────────────────────────────────── */
  .choices {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 560px;
    margin: 0 auto 12px;
  }
  .choice-btn {
    width: 100%;
    padding: 14px 16px;
    border-radius: 18px;
    background: var(--surface);
    border: 1.5px solid var(--border);
    color: var(--ink);
    font-size: 14px;
    font-weight: 700;
    text-align: left;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s, opacity 0.15s;
  }
  .choice-btn:hover:not(:disabled) {
    background: var(--surface-2);
    border-color: var(--border-strong);
  }
  .choice-btn.correct {
    background: color-mix(in oklab, var(--mint) 18%, var(--surface));
    border-color: var(--mint);
    color: var(--mint);
  }
  .choice-btn.wrong {
    background: color-mix(in oklab, var(--rose) 18%, var(--surface));
    border-color: var(--rose);
    color: var(--rose);
  }
  .choice-btn.dimmed { opacity: 0.4; }

  .single-action {
    display: flex;
    justify-content: center;
    padding: 8px 0 12px;
  }
  .single-action button {
    min-width: 12rem;
    padding: 14px 20px;
    font-size: 15px;
    font-weight: 800;
    border-radius: 18px;
    background: var(--gradient-brand);
    color: #fff;
    border: none;
    box-shadow: var(--shadow-sm);
  }
  :global([data-theme='washi']) .single-action button { color: #2B231A; }

  .encourage {
    margin-top: 16px;
    padding: 10px 14px;
    background: var(--accent-soft);
    border-radius: 14px;
    font-size: 13px;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .encourage-icon { color: var(--accent); display: inline-flex; }

  .jump {
    text-align: center;
    padding: 12px 0 4px;
    font-size: 13px;
  }

  .center {
    padding: 2rem;
    text-align: center;
  }
  .muted { color: var(--muted); }

  @media (max-width: 420px) {
    .big-glyph { font-size: 128px; }
  }
</style>
