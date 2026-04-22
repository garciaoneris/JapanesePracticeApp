<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { bundle } from '../lib/data/bundle';
  import { getAllBestScores, getMeta } from '../lib/data/db';
  import { isNativeMode, quizScoreKey, reviewScoreKey } from '../lib/data/mode';
  import { getMistakeCount } from '../lib/data/mistakes';
  import { speakJa } from '../lib/speech/tts';

  import Petal from '../lib/ui/Petal.svelte';
  import Blossom from '../lib/ui/Blossom.svelte';
  import Flame from '../lib/ui/Flame.svelte';
  import PetalField from '../lib/ui/PetalField.svelte';
  import GoalRing from '../lib/ui/GoalRing.svelte';
  import KanjiTile, { type TileTier } from '../lib/ui/KanjiTile.svelte';

  import { getXpState, type XpState } from '../lib/gamification/xp';
  import { getGoalState, type GoalState } from '../lib/gamification/goal';
  import { getStreakState } from '../lib/gamification/streak';
  import { resolveKotd } from '../lib/gamification/kotd';
  import { getDisplayName } from '../lib/gamification/displayName';

  // ── Curriculum ordering (unchanged from prior Home) ───────────────
  const b = bundle();
  const kanjiList = $derived(
    Object.values(b.kanji).sort((a, c) => {
      if (c.jlpt !== a.jlpt) return c.jlpt - a.jlpt;
      const ag = a.grade || 99;
      const cg = c.grade || 99;
      if (ag !== cg) return ag - cg;
      return a.strokes - c.strokes;
    }),
  );
  const counts = $derived({
    kanji: Object.keys(b.kanji).length,
    words: Object.keys(b.words).length,
  });

  // ── Level filter (Lvl 1..5; no "all" in the redesign) ─────────────
  type Level = 1 | 2 | 3 | 4 | 5;
  const FILTER_KEY = 'home-jlpt-filter';
  const LEVEL_JLPT: Record<Level, number[]> = {
    1: [5], 2: [4], 3: [3, 2], 4: [1], 5: [0],
  };
  function loadFilter(): Level {
    const v = sessionStorage.getItem(FILTER_KEY);
    const n = Number(v);
    return [1, 2, 3, 4, 5].includes(n) ? (n as Level) : 1;
  }
  let filter = $state<Level>(loadFilter());
  $effect(() => { sessionStorage.setItem(FILTER_KEY, String(filter)); });
  const filtered = $derived(
    kanjiList.filter((k) => LEVEL_JLPT[filter].includes(k.jlpt)),
  );

  // ── Scores (unchanged semantics) ─────────────────────────────────
  let bestScores = $state<Map<string, number>>(new Map());
  let quizScores = $state<Map<string, number>>(new Map());
  let reviewScores = $state<Map<string, number>>(new Map());
  let mistakeCount = $state(0);

  const masteredCount = $derived([...bestScores.values()].filter((v) => v >= 80).length);
  const goldCount = $derived([...bestScores.values()].filter((v) => v >= 85).length);

  // ── Gamification state ────────────────────────────────────────────
  let xpState = $state<XpState>({ xp: 0, level: 1, intoLevel: 0, levelSpan: 200 });
  let goalState = $state<GoalState>({ goalMinutes: 10, todayMinutes: 0, todayDate: '' });
  let streakDays = $state(0);
  let displayName = $state('');
  let kotdChar = $state('');
  let dueCount = $state(0);

  // ── Due count for the Review action card ──────────────────────────
  async function countDueAndFill(): Promise<number> {
    const { dueSrs } = await import('../lib/data/db');
    const due = await dueSrs(Date.now(), 200);
    return due.length;
  }

  onMount(async () => {
    bestScores = await getAllBestScores();

    if (await isNativeMode()) {
      for (const ch of Object.keys(b.kanji)) {
        if (!bestScores.has(ch)) bestScores.set(ch, 80);
      }
      bestScores = new Map(bestScores);
    }

    const [qk, rk] = await Promise.all([quizScoreKey(), reviewScoreKey()]);
    const [qs, rs] = await Promise.all([
      getMeta<Record<string, number>>(qk),
      getMeta<Record<string, number>>(rk),
    ]);
    if (qs) quizScores = new Map(Object.entries(qs));
    if (rs) reviewScores = new Map(Object.entries(rs));

    mistakeCount = await getMistakeCount();

    xpState = await getXpState();
    goalState = await getGoalState();
    const s = await getStreakState();
    streakDays = s.streakDays;
    displayName = await getDisplayName();

    const mastered = new Set([...bestScores.entries()].filter(([, v]) => v >= 80).map(([k]) => k));
    kotdChar = await resolveKotd(Object.keys(b.kanji), mastered);

    dueCount = await countDueAndFill();
  });

  // ── Tile tier derivation (same logic as before, returned as TileTier) ─
  function tileTier(char: string): TileTier {
    const stroke = bestScores.get(char) ?? 0;
    const quiz = quizScores.get(char) ?? -1;
    const review = reviewScores.get(char) ?? -1;

    if (stroke === 0 && quiz < 0 && review < 0) return 'new';
    if (stroke < 80) return 'progress';
    if (review >= 0 && review < 100) return 'review';
    const perfectQuiz = quiz === 100;
    const perfectReview = review === 100;
    if (stroke >= 85 && perfectQuiz && perfectReview) return 'platinum';
    if (stroke >= 85 && (perfectQuiz || perfectReview)) return 'gold';
    if (stroke >= 85) return 'gold-edge';
    return 'green';
  }

  /** Primary reading for a tile: on'yomi first (katakana → hiragana),
   *  fall back to kun'yomi. Strip okurigana markers and prefix dashes. */
  function primaryReading(kun: string[], on: string[]): string {
    const clean = (s: string) => s.replace(/[.\-]/g, '').trim();
    const toHira = (s: string) =>
      [...s].map((c) => {
        const cp = c.codePointAt(0)!;
        return cp >= 0x30a1 && cp <= 0x30f6 ? String.fromCodePoint(cp - 0x60) : c;
      }).join('');
    for (const r of on) { const c = clean(r); if (c) return toHira(c); }
    for (const r of kun) { const c = clean(r); if (c) return c; }
    return '';
  }

  // ── Greeting + date header ───────────────────────────────────────
  const headerDate = $derived.by(() => {
    const d = new Date();
    const wd = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][d.getDay()];
    const mo = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
    return `${wd} · ${mo} ${d.getDate()}`;
  });
  const greeting = $derived(displayName ? `おかえり, ${displayName}` : 'おかえり');

  // ── Hero microcopy based on progress ──────────────────────────────
  const goalPct = $derived(Math.min(1, goalState.todayMinutes / Math.max(1, goalState.goalMinutes)));
  const goalLine = $derived.by(() => {
    const remain = Math.max(0, Math.ceil(goalState.goalMinutes - goalState.todayMinutes));
    if (goalState.todayMinutes === 0) return "Let's get started today.";
    if (remain === 0) return "Goal complete. Keep the rhythm.";
    return `${remain} more minute${remain === 1 ? '' : 's'} to hit your goal.`;
  });
  const streakLine = $derived.by(() => {
    if (streakDays === 0) return "Start a streak — hit your goal today.";
    if (streakDays < 7) return `You're on a ${streakDays}-day streak. Keep it going.`;
    if (streakDays < 30) return `Keep going — you're building a ${streakDays}-day streak.`;
    return `A ${streakDays}-day streak. That's rare.`;
  });

  // ── Review action-card line ──────────────────────────────────────
  const reviewSub = $derived.by(() => {
    if (dueCount === 0) return 'All caught up';
    const mins = Math.max(1, Math.ceil(dueCount * 0.3));
    return `${dueCount} card${dueCount === 1 ? '' : 's'} due · ~${mins} min`;
  });

  // ── Kanji-of-the-day details ─────────────────────────────────────
  const kotd = $derived(kotdChar ? b.kanji[kotdChar] : null);
  const kotdReading = $derived.by(() => {
    if (!kotd) return '';
    const on = kotd.on.slice(0, 1).map((r) => r.replace(/[.\-]/g, '').trim()).filter(Boolean);
    const kun = kotd.kun.slice(0, 1).map((r) => r.replace(/[.\-]/g, '').trim()).filter(Boolean);
    return [...kun, ...on].join(' · ');
  });
  const kotdMeaning = $derived(kotd ? kotd.meanings.slice(0, 2).join(' · ') : '');

  function hearKotd() {
    if (!kotd) return;
    const r = kotd.kun[0] ?? kotd.on[0] ?? kotd.char;
    speakJa(r.replace(/[.\-]/g, ''));
  }

  // ── XP bar ───────────────────────────────────────────────────────
  const xpBarPct = $derived(
    xpState.levelSpan > 0 ? Math.min(1, xpState.intoLevel / xpState.levelSpan) : 0,
  );
  const xpLine = $derived(
    `${xpState.intoLevel.toLocaleString()} / ${xpState.levelSpan.toLocaleString()} XP`,
  );
</script>

<div class="screen">
  <!-- ── Top bar ──────────────────────────────────────────────── -->
  <header class="topbar">
    <div class="brand">
      <div class="logo jp-serif">日</div>
      <div>
        <div class="date">{headerDate}</div>
        <div class="greeting">{greeting}</div>
      </div>
    </div>
    <div class="top-actions">
      <div class="streak-pill">
        <Flame size={18} />
        <span class="tnum">{streakDays}</span>
      </div>
      <a class="gear" href="/settings" use:link aria-label="Settings">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </a>
    </div>
  </header>

  <!-- ── Hero card: goal ring + XP ──────────────────────────── -->
  <section class="hero">
    <PetalField count={10} />

    <div class="hero-row">
      <GoalRing pct={goalPct} size={120} stroke={11} sublabel="min today">
        {#snippet label()}
          <span class="tnum">
            {goalState.todayMinutes.toFixed(goalState.todayMinutes < 10 ? 1 : 0)}<span class="denom">/{goalState.goalMinutes}</span>
          </span>
        {/snippet}
      </GoalRing>

      <div class="hero-copy">
        <div class="kicker">
          <Petal size={10} />
          Today's goal
        </div>
        <div class="hero-line jp-serif">{goalLine}</div>
        <div class="hero-sub">{streakLine}</div>
      </div>
    </div>

    <div class="xp-row">
      <div class="level-pill">
        <span class="bloom-icon"><Blossom size={16} /></span>
        Lv {xpState.level}
      </div>
      <div class="xp-bar"><div class="xp-fill" style="width: {xpBarPct * 100}%;"></div></div>
      <div class="xp-numbers tnum">{xpLine}</div>
    </div>
  </section>

  <!-- ── Action cards ─────────────────────────────────────────── -->
  <div class="actions">
    <a class="action action-primary" href="/review" use:link>
      <div class="action-bloom" aria-hidden="true"><Blossom size={90} /></div>
      <div class="action-icon action-icon-primary">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>
      </div>
      <div class="action-title">Review Lvl {filter}</div>
      <div class="action-sub">{reviewSub}</div>
    </a>
    <a class="action" href="/vocabulary" use:link>
      <div class="action-icon">📘</div>
      <div class="action-title">Vocabulary</div>
      <div class="action-sub">{counts.words.toLocaleString()} words</div>
    </a>
    <a class="action" href="/fill-kanji" use:link>
      <div class="action-icon">✏️</div>
      <div class="action-title">Fill Lvl {filter}</div>
      <div class="action-sub">Practice 5</div>
    </a>
  </div>

  {#if mistakeCount > 0}
    <a class="reinforce-strip" href="/reinforce" use:link>
      <span>💪</span>
      <span>Reinforce {mistakeCount} open mistake{mistakeCount === 1 ? '' : 's'}</span>
      <span class="arrow">→</span>
    </a>
  {/if}

  <!-- ── Kanji of the day ─────────────────────────────────────── -->
  {#if kotd}
    <div class="kotd">
      <div class="kotd-bloom" aria-hidden="true"><Blossom size={220} /></div>
      <div class="kotd-tile">
        <div class="kotd-glyph jp-serif">{kotd.char}</div>
        <div class="kotd-badge">Today</div>
      </div>
      <div class="kotd-body">
        <div class="kotd-kicker">Kanji of the day</div>
        <div class="kotd-meaning">{kotdMeaning}</div>
        <div class="kotd-reading jp-sans">{kotdReading}</div>
        <div class="kotd-ctas">
          <a class="btn-primary" href={`/learn/${encodeURIComponent(kotd.char)}`} use:link>Learn now</a>
          <button class="btn-ghost" onclick={hearKotd} aria-label="Hear reading">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M11 5L6 9H2v6h4l5 4V5z"/>
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
            </svg>
            Hear it
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- ── Stats row ────────────────────────────────────────────── -->
  <div class="stats">
    <div class="stat"><span class="stat-icon">🌸</span><div><div class="stat-label">Mastered</div><div class="stat-value tnum">{masteredCount}<span class="stat-denom">/{counts.kanji}</span></div></div></div>
    <div class="stat"><span class="stat-icon">✨</span><div><div class="stat-label">Gold</div><div class="stat-value tnum">{goldCount}</div></div></div>
    <div class="stat"><span class="stat-icon">🔥</span><div><div class="stat-label">Streak</div><div class="stat-value tnum">{streakDays}</div></div></div>
    <div class="stat"><span class="stat-icon">📚</span><div><div class="stat-label">Words</div><div class="stat-value tnum">{counts.words.toLocaleString()}</div></div></div>
  </div>

  <!-- ── Kanji grid ──────────────────────────────────────────── -->
  <div class="grid-head">
    <div class="grid-kicker">Your Kanji · {filtered.length}</div>
    <div class="filters">
      {#each [1, 2, 3, 4, 5] as n (n)}
        <button class="chip" class:active={filter === n} onclick={() => (filter = n as Level)}>L{n}</button>
      {/each}
    </div>
  </div>

  <div class="grid">
    {#each filtered as k (k.char)}
      <a class="grid-cell" href={`/learn/${encodeURIComponent(k.char)}`} use:link aria-label={k.meanings.join(', ')}>
        <KanjiTile
          char={k.char}
          reading={primaryReading(k.kun, k.on)}
          score={bestScores.has(k.char) ? bestScores.get(k.char)! : null}
          tier={tileTier(k.char)}
        />
      </a>
    {/each}
  </div>
</div>

<style>
  .screen {
    max-width: 820px;
    margin: 0 auto;
    padding: 16px 16px 48px;
  }

  /* ── Top bar ─────────────────────────────────────────────── */
  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .logo {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: var(--gradient-brand);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    font-weight: 700;
    box-shadow: var(--shadow-sm);
  }
  .date {
    font-size: 11px;
    color: var(--muted);
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .greeting {
    font-size: 18px;
    font-weight: 800;
    color: var(--ink);
    margin-top: 2px;
  }
  .top-actions { display: flex; align-items: center; gap: 10px; }
  .streak-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    border-radius: 999px;
    background: linear-gradient(135deg, #FF8A4C, #E6453C);
    color: white;
    font-weight: 800;
    font-size: 14px;
    box-shadow: 0 6px 16px rgba(230, 70, 50, 0.35);
  }
  .gear {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--ink-2);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* ── Hero card ───────────────────────────────────────────── */
  .hero {
    position: relative;
    border-radius: 28px;
    background: var(--hero-grad);
    padding: 22px;
    box-shadow: var(--shadow-md);
    border: 1px solid var(--border);
    overflow: hidden;
    margin-bottom: 16px;
  }
  .hero-row {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 18px;
  }
  .hero-copy { flex: 1; min-width: 0; }
  .kicker {
    font-size: 11px;
    font-weight: 800;
    color: var(--ink-2);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 4px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .kicker :global(svg) { color: var(--accent); }
  .hero-line {
    font-size: 22px;
    font-weight: 600;
    line-height: 1.15;
    margin-bottom: 8px;
    color: var(--ink);
  }
  .hero-sub {
    font-size: 13px;
    color: var(--ink-2);
    line-height: 1.4;
  }
  .denom {
    font-size: 0.45em;
    font-weight: 600;
    color: var(--ink-2);
    margin-left: 2px;
  }

  .xp-row {
    position: relative;
    z-index: 1;
    margin-top: 16px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .level-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid var(--border);
    font-weight: 800;
    font-size: 13px;
    color: var(--ink);
    /* backdrop-filter dropped for iPad compositor budget — solid fill
       covers what we need over the hero-grad. */
  }
  .bloom-icon { color: var(--accent-2); display: flex; }
  :global([data-theme='neon']) .level-pill { background: rgba(255, 255, 255, 0.1); }
  .xp-bar {
    flex: 1;
    height: 10px;
    background: rgba(255, 255, 255, 0.35);
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  :global([data-theme='neon']) .xp-bar { background: rgba(255, 255, 255, 0.08); }
  .xp-fill {
    height: 100%;
    background: var(--gradient-brand);
    border-radius: 999px;
    box-shadow: 0 0 12px color-mix(in oklab, var(--accent) 60%, transparent);
  }
  .xp-numbers {
    font-size: 12px;
    font-weight: 700;
    color: var(--ink-2);
    white-space: nowrap;
  }

  /* ── Action cards ────────────────────────────────────────── */
  .actions {
    display: grid;
    grid-template-columns: 1.6fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 16px;
  }
  .action {
    position: relative;
    padding: 14px;
    border-radius: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    color: var(--ink);
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 92px;
    overflow: hidden;
  }
  .action-primary {
    background: var(--gradient-brand);
    color: #fff;
    border: none;
    box-shadow: 0 12px 28px color-mix(in oklab, var(--accent) 30%, transparent);
    padding: 18px;
  }
  :global([data-theme='washi']) .action-primary { color: #2B231A; }
  .action-bloom {
    position: absolute;
    right: -20px;
    bottom: -20px;
    opacity: 0.2;
    color: currentColor;
    pointer-events: none;
  }
  .action-icon {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
  }
  .action-icon-primary {
    background: rgba(255, 255, 255, 0.22);
    color: currentColor;
  }
  .action-title {
    font-weight: 800;
    font-size: 14px;
  }
  .action-primary .action-title { font-size: 17px; }
  .action-sub {
    font-size: 11px;
    font-weight: 600;
    opacity: 0.7;
    margin-top: 2px;
  }
  .action-primary .action-sub { opacity: 0.88; }

  /* ── Reinforce strip ─────────────────────────────────────── */
  .reinforce-strip {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    margin-bottom: 16px;
    border-radius: 14px;
    background: color-mix(in oklab, var(--rose) 10%, var(--surface));
    border: 1px solid color-mix(in oklab, var(--rose) 40%, transparent);
    color: var(--ink);
    font-size: 13px;
    font-weight: 700;
  }
  .reinforce-strip .arrow { margin-left: auto; color: var(--rose); }

  /* ── Kanji of the day ────────────────────────────────────── */
  .kotd {
    position: relative;
    border-radius: 22px;
    padding: 18px;
    margin-bottom: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: center;
    gap: 16px;
    overflow: hidden;
  }
  .kotd-bloom {
    position: absolute;
    right: -40px;
    top: -30px;
    color: var(--accent);
    opacity: 0.1;
    pointer-events: none;
  }
  .kotd-tile {
    width: 104px;
    height: 104px;
    background: var(--tile-mastered);
    border: 1.5px solid var(--border-strong);
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    flex-shrink: 0;
  }
  .kotd-glyph {
    font-size: 62px;
    color: var(--ink);
    line-height: 1;
  }
  .kotd-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: var(--gradient-brand);
    color: #fff;
    font-size: 10px;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 999px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    box-shadow: var(--shadow-sm);
  }
  .kotd-body { flex: 1; position: relative; z-index: 1; min-width: 0; }
  .kotd-kicker {
    font-size: 10px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  .kotd-meaning {
    font-size: 18px;
    font-weight: 800;
    color: var(--ink);
    margin-bottom: 2px;
    line-height: 1.2;
  }
  .kotd-reading {
    font-size: 14px;
    color: var(--ink-2);
    margin-bottom: 10px;
  }
  .kotd-ctas { display: flex; gap: 8px; flex-wrap: wrap; }
  .btn-primary {
    padding: 9px 16px;
    font-size: 13px;
    border-radius: 12px;
    background: var(--gradient-brand);
    color: #fff;
    font-weight: 700;
    border: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  :global([data-theme='washi']) .btn-primary { color: #2B231A; }
  .btn-ghost {
    padding: 9px 14px;
    font-size: 13px;
    border-radius: 12px;
    background: transparent;
    border: 1px solid var(--border-strong);
    color: var(--ink);
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  /* ── Stats ──────────────────────────────────────────────── */
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 20px;
  }
  .stat {
    padding: 12px;
    border-radius: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .stat-icon { font-size: 20px; }
  .stat-label {
    font-size: 10px;
    color: var(--muted);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .stat-value {
    font-weight: 800;
    font-size: 16px;
    color: var(--ink);
  }
  .stat-denom {
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
  }

  /* ── Grid head + chips ──────────────────────────────────── */
  .grid-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding: 0 4px;
    gap: 8px;
    flex-wrap: wrap;
  }
  .grid-kicker {
    font-size: 12px;
    font-weight: 800;
    color: var(--muted);
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .filters { display: flex; gap: 6px; }
  .chip {
    padding: 6px 12px;
    border-radius: 999px;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--ink-2);
    font-size: 12px;
    font-weight: 700;
  }
  .chip.active {
    background: var(--ink);
    color: var(--surface);
    border-color: var(--ink);
  }
  :global([data-theme='washi']) .chip.active,
  :global([data-theme='sakura']) .chip.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }

  /* ── Grid ───────────────────────────────────────────────── */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
    gap: 8px;
  }
  .grid-cell {
    text-decoration: none;
    /* Off-screen tiles skip paint, layout, and style — huge scroll
       win on L3 where the filter can produce 500+ tiles. The intrinsic
       size hint matches the tile aspect so the scrollbar doesn't jump
       as cells cross the viewport boundary. */
    content-visibility: auto;
    contain-intrinsic-size: 82px 104px;
  }
  .grid-cell :global(.tile) { width: 100% !important; aspect-ratio: 1 / 1; height: auto !important; }

  @media (max-width: 480px) {
    .actions { grid-template-columns: 1fr 1fr; }
    .action-primary { grid-column: span 2; }
    .stats { grid-template-columns: repeat(2, 1fr); }
  }
</style>
