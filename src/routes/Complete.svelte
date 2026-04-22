<script lang="ts">
  import { onMount } from 'svelte';
  import { link, push } from 'svelte-spa-router';
  import Blossom from '../lib/ui/Blossom.svelte';
  import Flame from '../lib/ui/Flame.svelte';
  import PetalField from '../lib/ui/PetalField.svelte';
  import Confetti from '../lib/ui/Confetti.svelte';

  interface EarnedBadge { id: string; title: string; criteria: string; }
  interface SessionSummary {
    reviews: number;
    correct: number;
    bestStreak: number;
    durationSec: number;
    xpGained: number;
    levelUp: { from: number; to: number } | null;
    justHitGoal: boolean;
    goalMinutes: number;
    streakDays: number;
    earnedBadges: EarnedBadge[];
  }

  /** Fallback if someone lands on /complete without a preceding Review —
   *  e.g. a cold-start navigation. Shows a neutral celebration rather than
   *  erroring out. */
  const FALLBACK: SessionSummary = {
    reviews: 0,
    correct: 0,
    bestStreak: 0,
    durationSec: 0,
    xpGained: 0,
    levelUp: null,
    justHitGoal: false,
    goalMinutes: 10,
    streakDays: 0,
    earnedBadges: [],
  };

  let summary = $state<SessionSummary>(FALLBACK);

  onMount(() => {
    const raw = sessionStorage.getItem('review-session-summary');
    if (raw) {
      try {
        summary = { ...FALLBACK, ...JSON.parse(raw) };
      } catch {
        // Corrupted cache — fall back silently.
      }
    }
  });

  // ── Derived copy + display values ────────────────────────────────
  const minutesLine = $derived.by(() => {
    const m = summary.durationSec / 60;
    if (m < 1) return `${Math.round(summary.durationSec)}s`;
    if (m < 10) return `${m.toFixed(1)}m`;
    return `${Math.round(m)}m`;
  });

  const subline = $derived.by(() => {
    if (summary.reviews === 0) return "Welcome. Ready when you are.";
    const perfect = summary.correct;
    if (summary.bestStreak >= 7) {
      return `${summary.reviews} reviews, ${perfect} correct. You're in flow.`;
    }
    if (perfect === summary.reviews) {
      return `${summary.reviews} reviews, all correct. Clean session.`;
    }
    return `${summary.reviews} reviews, ${perfect} correct. Keep the rhythm.`;
  });

  /** Hours-and-minutes until midnight local, for the footer copy. */
  const timeUntilMidnight = $derived.by(() => {
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setHours(24, 0, 0, 0);
    const diffMs = tomorrow.getTime() - now.getTime();
    const hrs = Math.floor(diffMs / 3_600_000);
    const mins = Math.floor((diffMs % 3_600_000) / 60_000);
    return `${hrs}h ${mins}m`;
  });

  const xpDisplay = $derived(summary.xpGained > 0 ? `+${summary.xpGained}` : '0');

  function keepGoing(): void {
    // Clear the summary so re-visits don't stale-repeat the celebration.
    sessionStorage.removeItem('review-session-summary');
    push('/review');
  }
  function goHome(): void {
    sessionStorage.removeItem('review-session-summary');
    push('/');
  }
</script>

<div class="screen">
  <Confetti count={26} />

  <!-- Close button -->
  <div class="close-row">
    <a class="close" href="/" use:link aria-label="Close" onclick={() => sessionStorage.removeItem('review-session-summary')}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </a>
  </div>

  <!-- ── Hero ──────────────────────────────────────────────── -->
  <section class="hero">
    <PetalField count={12} />

    <div class="hero-inner">
      <div class="blossom-badge">
        <div class="blossom-ring animate-breathe"><Blossom size={82} /></div>
      </div>

      <div class="kicker">Session complete</div>
      <div class="greeting jp-serif">お疲れさま!</div>
      <div class="subline">{subline}</div>

      <div class="stats">
        <div class="stat">
          <div class="stat-icon stat-accent"><Blossom size={18} /></div>
          <div class="stat-value tnum">{xpDisplay}</div>
          <div class="stat-label">XP earned</div>
        </div>
        <div class="stat">
          <div class="stat-icon stat-sky">⏱</div>
          <div class="stat-value tnum">{minutesLine}</div>
          <div class="stat-label">Time spent</div>
        </div>
        <div class="stat">
          <div class="stat-icon stat-flame"><Flame size={18} /></div>
          <div class="stat-value tnum">{summary.streakDays}</div>
          <div class="stat-label">Day streak</div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── Level-up banner ──────────────────────────────────── -->
  {#if summary.levelUp}
    <div class="level-up">
      <div class="level-bloom" aria-hidden="true"><Blossom size={130} /></div>
      <div class="level-inner">
        <div class="level-num tnum">{summary.levelUp.to}</div>
        <div class="level-body">
          <div class="level-kicker">Level up!</div>
          <div class="level-title tnum">Lv {summary.levelUp.from} → Lv {summary.levelUp.to}</div>
          <div class="level-sub">More brightness across your mastered tiles.</div>
        </div>
      </div>
    </div>
  {/if}

  <!-- ── Goal-hit banner ─────────────────────────────────── -->
  {#if summary.justHitGoal}
    <div class="goal-hit">
      <span class="goal-hit-icon">🌸</span>
      <div>
        <div class="goal-hit-title">Daily goal hit</div>
        <div class="goal-hit-sub">{summary.goalMinutes} min today · streak extended</div>
      </div>
    </div>
  {/if}

  <!-- ── Badge unlocks ────────────────────────────────────── -->
  {#each summary.earnedBadges as badge (badge.id)}
    <div class="badge-card">
      <div class="badge-tile"><Blossom size={32} /></div>
      <div class="badge-body">
        <div class="badge-kicker">Badge unlocked</div>
        <div class="badge-title">{badge.title}</div>
        <div class="badge-sub">{badge.criteria}</div>
      </div>
    </div>
  {/each}

  <!-- ── CTAs ─────────────────────────────────────────────── -->
  <div class="ctas">
    <button class="cta-primary" onclick={keepGoing}>Keep going →</button>
    <button class="cta-ghost" onclick={goHome}>Home</button>
  </div>

  <div class="footer">
    Tomorrow's goal unlocks in <b class="tnum">{timeUntilMidnight}</b>
  </div>
</div>

<style>
  .screen {
    position: relative;
    max-width: 640px;
    margin: 0 auto;
    padding: 16px 16px 48px;
    min-height: 100vh;
  }

  .close-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 8px;
    position: relative;
    z-index: 2;
  }
  .close {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--ink-2);
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  /* ── Hero ───────────────────────────────────────────────── */
  .hero {
    position: relative;
    border-radius: 26px;
    background: var(--hero-grad);
    padding: 24px 20px 28px;
    border: 1px solid var(--border);
    box-shadow: var(--shadow-md);
    overflow: hidden;
    margin-bottom: 16px;
  }
  .hero-inner { position: relative; z-index: 1; text-align: center; }
  .blossom-badge {
    display: flex;
    justify-content: center;
    margin-bottom: 12px;
  }
  .blossom-ring {
    width: 112px;
    height: 112px;
    border-radius: 50%;
    background: var(--surface);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent);
    box-shadow:
      0 0 0 6px color-mix(in oklab, var(--accent) 18%, transparent),
      var(--shadow-md);
  }
  .kicker {
    font-size: 11px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .greeting {
    font-size: 34px;
    font-weight: 600;
    color: var(--ink);
    line-height: 1.15;
    margin-bottom: 6px;
  }
  .subline {
    font-size: 15px;
    color: var(--ink-2);
    margin-bottom: 20px;
    padding: 0 8px;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .stat {
    padding: 12px 8px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.6);
    border: 1px solid var(--border);
    backdrop-filter: blur(8px);
    text-align: center;
  }
  :global([data-theme='neon']) .stat {
    background: rgba(0, 0, 0, 0.35);
  }
  .stat-icon {
    display: flex;
    justify-content: center;
    margin-bottom: 4px;
    font-size: 16px;
  }
  .stat-accent { color: var(--accent); }
  .stat-sky    { color: var(--sky); }
  .stat-flame  { color: #E6453C; }
  .stat-value {
    font-weight: 800;
    font-size: 18px;
    color: var(--ink);
  }
  .stat-label {
    font-size: 10px;
    color: var(--muted);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 2px;
  }

  /* ── Level up ───────────────────────────────────────────── */
  .level-up {
    padding: 16px;
    border-radius: 20px;
    background: var(--gradient-brand);
    color: #fff;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 12px 24px color-mix(in oklab, var(--accent) 35%, transparent);
  }
  :global([data-theme='washi']) .level-up { color: #2B231A; }
  .level-bloom {
    position: absolute;
    right: -18px;
    top: -12px;
    opacity: 0.25;
    color: inherit;
    pointer-events: none;
  }
  .level-inner {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .level-num {
    width: 46px;
    height: 46px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.22);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 20px;
    flex-shrink: 0;
  }
  .level-body { flex: 1; }
  .level-kicker {
    font-size: 10px;
    font-weight: 800;
    opacity: 0.85;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .level-title { font-weight: 800; font-size: 16px; }
  .level-sub { font-size: 12px; opacity: 0.9; }

  /* ── Goal-hit banner ────────────────────────────────────── */
  .goal-hit {
    padding: 12px 14px;
    border-radius: 16px;
    background: color-mix(in oklab, var(--mint) 16%, var(--surface));
    border: 1px solid color-mix(in oklab, var(--mint) 40%, transparent);
    color: var(--ink);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .goal-hit-icon { font-size: 24px; }
  .goal-hit-title { font-weight: 800; font-size: 14px; }
  .goal-hit-sub { font-size: 12px; color: var(--ink-2); }

  /* ── Badge card ─────────────────────────────────────────── */
  .badge-card {
    padding: 14px;
    border-radius: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .badge-tile {
    width: 56px;
    height: 56px;
    border-radius: 14px;
    background: var(--tile-gold);
    border: 1.5px solid rgba(230, 160, 40, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #3A2810;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
    flex-shrink: 0;
  }
  .badge-body { flex: 1; min-width: 0; }
  .badge-kicker {
    font-size: 11px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .badge-title {
    font-weight: 800;
    font-size: 15px;
    color: var(--ink);
  }
  .badge-sub {
    font-size: 12px;
    color: var(--ink-2);
  }

  /* ── CTAs + footer ──────────────────────────────────────── */
  .ctas {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .cta-primary,
  .cta-ghost {
    padding: 16px 20px;
    border-radius: 18px;
    font-weight: 800;
    font-size: 15px;
    cursor: pointer;
  }
  .cta-primary {
    flex: 1;
    background: var(--gradient-brand);
    color: #fff;
    border: none;
    box-shadow: 0 8px 20px color-mix(in oklab, var(--accent) 35%, transparent);
  }
  :global([data-theme='washi']) .cta-primary { color: #2B231A; }
  .cta-ghost {
    background: transparent;
    border: 1px solid var(--border-strong);
    color: var(--ink);
  }

  .footer {
    text-align: center;
    font-size: 12px;
    color: var(--muted);
    margin-top: 14px;
  }
  .footer b { color: var(--ink); }
</style>
