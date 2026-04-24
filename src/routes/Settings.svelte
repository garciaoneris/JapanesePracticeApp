<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { getToken, setToken, clearToken, syncNow, getLastSync, schedulePush } from '../lib/data/sync';
  import { getMeta, putMeta, getAllBestScores } from '../lib/data/db';
  import { setNativeModeCache } from '../lib/data/mode';
  import type { ClearedMistake, Mistake } from '../lib/data/mistakes';
  import { getFuriganaMode, setFuriganaMode, type FuriganaMode } from '../lib/data/furiganaMode';
  import { getDisplayName, setDisplayName } from '../lib/gamification/displayName';
  import { getGoalState, setGoalMinutes } from '../lib/gamification/goal';
  import { getStreakState } from '../lib/gamification/streak';
  type Theme = 'washi' | 'neon' | 'sakura';
  const THEMES: { id: Theme; name: string; subtitle: string; swatch: [string, string, string] }[] = [
    { id: 'washi',  name: 'Warm Washi', subtitle: 'Paper & sunset — calm & traditional', swatch: ['#FBF4E6', '#E76A3A', '#F2B138'] },
    { id: 'neon',   name: 'Neon City',  subtitle: 'Late-night study — dark with glow',   swatch: ['#0B0D1C', '#FF4D8F', '#7C5CFF'] },
    { id: 'sakura', name: 'Sakura',     subtitle: 'Pastel spring — bright & friendly',   swatch: ['#FFF3F6', '#FF6FA5', '#FFB070'] },
  ];
  let currentTheme = $state<Theme>('washi');

  async function selectTheme(t: Theme): Promise<void> {
    currentTheme = t;
    document.documentElement.setAttribute('data-theme', t);
    await putMeta('theme', t);
    schedulePush();
  }

  // ── Sync / token ─────────────────────────────────────────────
  let token = $state<string | null>(null);
  let tokenInput = $state('');
  let syncing = $state(false);
  let syncResult = $state<{ ok: boolean; error?: string } | null>(null);
  let lastSync = $state<number | null>(null);

  function maskToken(t: string): string {
    if (t.length <= 8) return '****';
    return t.slice(0, 4) + '****' + t.slice(-4);
  }
  function timeAgo(ts: number): string {
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} hr ago`;
    return `${Math.round(hrs / 24)} days ago`;
  }
  async function refreshState() {
    token = await getToken();
    lastSync = await getLastSync();
    syncResult = null;
    await refreshMistakeCounts();
  }

  // ── Mistakes ──────────────────────────────────────────────────
  let regularMistakeCount = $state(0);
  let nativeMistakeCount = $state(0);
  let clearingMistakes = $state(false);
  let clearMistakesResult = $state<string | null>(null);

  async function refreshMistakeCounts() {
    regularMistakeCount = ((await getMeta<Mistake[]>('mistakes')) ?? []).length;
    nativeMistakeCount = ((await getMeta<Mistake[]>('native-mistakes')) ?? []).length;
  }
  async function handleClearAllMistakes() {
    if (clearingMistakes) return;
    if (!confirm('Clear every open mistake on this device (regular + native)? This does NOT affect your scores or SRS state.')) return;
    clearingMistakes = true;
    clearMistakesResult = null;
    try {
      const now = Date.now();
      for (const [listKey, tombKey] of [
        ['mistakes', 'mistakes-cleared'] as const,
        ['native-mistakes', 'native-mistakes-cleared'] as const,
      ]) {
        const active = (await getMeta<Mistake[]>(listKey)) ?? [];
        if (active.length === 0) continue;
        const existing = (await getMeta<ClearedMistake[]>(tombKey)) ?? [];
        const byKey = new Map<string, ClearedMistake>();
        for (const c of existing) byKey.set(`${c.type}:${c.id}`, c);
        for (const m of active) {
          byKey.set(`${m.type}:${m.id}`, { type: m.type, id: m.id, clearedAt: now });
        }
        await putMeta(tombKey, [...byKey.values()]);
        await putMeta(listKey, []);
      }
      await refreshMistakeCounts();
      schedulePush();
      clearMistakesResult = 'All mistakes cleared. Sync scheduled.';
    } catch (e) {
      clearMistakesResult = `Failed: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      clearingMistakes = false;
    }
  }

  // ── Prefs ─────────────────────────────────────────────────────
  let furiganaMode = $state<FuriganaMode>(getFuriganaMode());
  let nativeMode = $state(false);
  let displayName = $state('');
  let goalMinutes = $state(10);

  async function handleFuriganaChange() {
    await setFuriganaMode(furiganaMode);
    schedulePush();
  }
  async function handleNativeToggle() {
    await putMeta('native-mode', nativeMode);
    setNativeModeCache(nativeMode);
    schedulePush();
    window.location.hash = '#/';
  }
  async function handleDisplayNameBlur() {
    await setDisplayName(displayName);
    schedulePush();
  }
  async function handleGoalChange() {
    const v = Math.max(1, Math.min(240, Math.round(goalMinutes)));
    goalMinutes = v;
    await setGoalMinutes(v);
    schedulePush();
  }

// ── Your progress snapshot ───────────────────────────────────
  let masteredCount = $state(0);
  let goldCount = $state(0);
  let streakDays = $state(0);

  async function refreshProgress(): Promise<void> {
    const scores = await getAllBestScores();
    const values = [...scores.values()];
    masteredCount = values.filter((v) => v >= 80).length;
    goldCount = values.filter((v) => v >= 85).length;
    const s = await getStreakState();
    streakDays = s.streakDays;
  }

  onMount(async () => {
    await refreshState();
    nativeMode = (await getMeta<boolean>('native-mode')) ?? false;
    furiganaMode = getFuriganaMode();
    const storedTheme = await getMeta<Theme>('theme');
    if (storedTheme && THEMES.some((t) => t.id === storedTheme)) currentTheme = storedTheme;
    displayName = await getDisplayName();
    const g = await getGoalState();
    goalMinutes = g.goalMinutes;
    await refreshProgress();
  });

  async function handleSave() {
    const trimmed = tokenInput.trim();
    if (!trimmed) return;
    await setToken(trimmed);
    tokenInput = '';
    await refreshState();
    syncing = true;
    syncResult = null;
    try {
      syncResult = await syncNow();
      lastSync = await getLastSync();
    } finally {
      syncing = false;
    }
  }
  async function handleSync() {
    syncing = true;
    syncResult = null;
    try {
      syncResult = await syncNow();
      lastSync = await getLastSync();
    } finally {
      syncing = false;
    }
  }
  async function handleRemove() {
    await clearToken();
    token = null;
    lastSync = null;
    syncResult = null;
    tokenInput = '';
  }
</script>

<div class="screen">
  <header class="topbar">
    <a class="back" href="/" use:link aria-label="Back">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </a>
    <h1>Settings</h1>
  </header>

  <!-- ── Appearance ────────────────────────────────────────── -->
  <div class="section-label">Appearance</div>
  <div class="theme-list">
    {#each THEMES as t (t.id)}
      <button
        class="theme-card"
        class:selected={currentTheme === t.id}
        onclick={() => selectTheme(t.id)}
      >
        <div class="theme-preview" style="background: {t.swatch[0]};">
          <div class="theme-preview-glow" style="background: radial-gradient(circle at 30% 30%, {t.swatch[1]}66, transparent 60%), radial-gradient(circle at 70% 80%, {t.swatch[2]}66, transparent 60%);"></div>
          <div class="theme-glyph jp-serif" class:dark-glyph={t.id === 'neon'}>桜</div>
        </div>
        <div class="theme-meta">
          <div class="theme-name">{t.name}</div>
          <div class="theme-sub">{t.subtitle}</div>
          <div class="theme-swatch">
            {#each t.swatch as c (c)}
              <span class="swatch-dot" style="background: {c};"></span>
            {/each}
          </div>
        </div>
        <div class="theme-radio" aria-hidden="true">
          {#if currentTheme === t.id}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          {/if}
        </div>
      </button>
    {/each}
  </div>

  <!-- ── Profile ──────────────────────────────────────────── -->
  <div class="section-label">Profile</div>
  <div class="card rows">
    <label class="row-input">
      <div class="row-icon">🌱</div>
      <div class="row-body">
        <div class="row-label">Display name</div>
        <input
          class="text-input"
          placeholder="Who should we greet?"
          bind:value={displayName}
          onblur={handleDisplayNameBlur}
          onkeydown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          maxlength="40"
        />
      </div>
    </label>
    <label class="row-input">
      <div class="row-icon">🎯</div>
      <div class="row-body">
        <div class="row-label">Daily goal</div>
        <div class="goal-input">
          <input
            class="text-input tnum"
            type="number"
            min="1"
            max="240"
            bind:value={goalMinutes}
            onblur={handleGoalChange}
            onkeydown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          />
          <span class="goal-unit">min / day</span>
        </div>
      </div>
    </label>
  </div>

  <!-- ── Learning ─────────────────────────────────────────── -->
  <div class="section-label">Learning</div>
  <div class="card">
    <div class="card-label">Furigana</div>
    <div class="radio-group">
      <label class="radio-row">
        <input type="radio" name="furigana-mode" value="always" bind:group={furiganaMode} onchange={handleFuriganaChange} />
        <span>Always show</span>
      </label>
      <label class="radio-row">
        <input type="radio" name="furigana-mode" value="hide-mastered" bind:group={furiganaMode} onchange={handleFuriganaChange} />
        <span>Hide on mastered kanji</span>
      </label>
      <label class="radio-row">
        <input type="radio" name="furigana-mode" value="never" bind:group={furiganaMode} onchange={handleFuriganaChange} />
        <span>Never show</span>
      </label>
    </div>
  </div>
  <div class="card tight">
    <label class="row-toggle">
      <div class="row-body">
        <div class="row-label">Native mode 🌻</div>
        <div class="row-sub">Treat all kanji as mastered. Unlocks all vocabulary and review content.</div>
      </div>
      <input type="checkbox" bind:checked={nativeMode} onchange={handleNativeToggle} />
    </label>
  </div>

<!-- ── Your progress ────────────────────────────────────── -->
  <div class="section-label">Your progress</div>
  <div class="card progress-card">
    <div class="progress-col">
      <div class="progress-val tnum">{masteredCount}</div>
      <div class="progress-label">Mastered</div>
    </div>
    <div class="progress-col bordered">
      <div class="progress-val tnum accent">{goldCount}</div>
      <div class="progress-label">Gold</div>
    </div>
    <div class="progress-col">
      <div class="progress-val tnum">{streakDays}d</div>
      <div class="progress-label">Streak</div>
    </div>
  </div>

  <!-- ── Gist sync ────────────────────────────────────────── -->
  <div class="section-label">Gist sync</div>
  <div class="card">
    {#if token}
      <div class="kv-row"><span class="kv-label">Token</span><span class="kv-val mono">{maskToken(token)}</span></div>
      <div class="kv-row"><span class="kv-label">Last synced</span><span class="kv-val">{lastSync ? timeAgo(lastSync) : 'Never synced'}</span></div>
      {#if syncResult}
        <div class="result" class:ok={syncResult.ok} class:fail={!syncResult.ok}>
          {syncResult.ok ? 'Synced successfully.' : `Sync failed: ${syncResult.error ?? 'unknown error'}`}
        </div>
      {/if}
      <div class="btn-row">
        <button class="btn-primary" onclick={handleSync} disabled={syncing}>
          {#if syncing}<span class="spinner"></span> Syncing…{:else}Sync now{/if}
        </button>
        <button class="btn-danger" onclick={handleRemove} disabled={syncing}>Remove token</button>
      </div>
    {:else}
      <p class="desc">
        Paste a GitHub Personal Access Token with the <code>gist</code> scope to sync your progress (scores, SRS, XP, streak, theme, badges…) across devices.
      </p>
      <p class="url-hint">Create a token at github.com/settings/tokens</p>
      <input type="password" class="text-input token" placeholder="ghp_..." bind:value={tokenInput} onkeydown={(e) => e.key === 'Enter' && handleSave()} />
      <div class="btn-row">
        <button class="btn-primary" onclick={handleSave} disabled={!tokenInput.trim()}>Save token</button>
      </div>
    {/if}
  </div>

  <!-- ── Reinforce / clear mistakes ───────────────────────── -->
  <div class="section-label">Reinforce</div>
  <div class="card">
    <div class="kv-row">
      <span class="kv-label">Open mistakes</span>
      <span class="kv-val">
        {regularMistakeCount} regular
        {#if nativeMistakeCount > 0} · {nativeMistakeCount} native{/if}
      </span>
    </div>
    <p class="desc">
      Wipes every open mistake on this device and writes tombstones so they don't return via sync. Scores, SRS state, and drawing history stay intact.
    </p>
    {#if clearMistakesResult}
      <div class="result" class:ok={!clearMistakesResult.startsWith('Failed')} class:fail={clearMistakesResult.startsWith('Failed')}>{clearMistakesResult}</div>
    {/if}
    <div class="btn-row">
      <button
        class="btn-danger"
        onclick={handleClearAllMistakes}
        disabled={clearingMistakes || (regularMistakeCount === 0 && nativeMistakeCount === 0)}
      >
        {clearingMistakes ? 'Clearing…' : 'Clear all mistakes'}
      </button>
    </div>
  </div>
</div>

<style>
  .screen { max-width: 640px; margin: 0 auto; padding: 16px 16px 48px; }

  .topbar { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
  .back {
    width: 36px; height: 36px; border-radius: 10px;
    border: 1px solid var(--border); background: var(--surface);
    color: var(--ink-2);
    display: inline-flex; align-items: center; justify-content: center;
  }
  h1 { font-size: 22px; font-weight: 800; color: var(--ink); margin: 0; }

  .section-label {
    font-size: 11px; font-weight: 800; color: var(--muted);
    letter-spacing: 0.14em; text-transform: uppercase;
    margin: 16px 4px 10px;
  }
  .section-label:first-of-type { margin-top: 0; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: var(--shadow-sm);
    color: var(--ink);
  }
  .card.tight { padding: 10px 14px; }
  .card.rows { padding: 4px 4px; }

  /* ── Theme picker ───────────────────────────────────── */
  .theme-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; }
  .theme-card {
    all: unset;
    padding: 12px; border-radius: 18px;
    background: var(--surface);
    border: 2px solid var(--border);
    display: flex; align-items: center; gap: 14px;
    box-shadow: var(--shadow-sm);
    cursor: pointer;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }
  .theme-card.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
  }
  .theme-preview {
    width: 68px; height: 68px; border-radius: 14px;
    position: relative; overflow: hidden;
    border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .theme-preview-glow { position: absolute; inset: 0; }
  .theme-glyph {
    position: relative; z-index: 1;
    font-size: 34px; font-weight: 500;
    color: #2B231A;
  }
  .theme-glyph.dark-glyph { color: #fff; }
  .theme-meta { flex: 1; min-width: 0; }
  .theme-name { font-weight: 800; font-size: 15px; color: var(--ink); }
  .theme-sub { font-size: 12px; color: var(--ink-2); margin-top: 2px; }
  .theme-swatch { display: flex; gap: 4px; margin-top: 6px; }
  .swatch-dot {
    width: 16px; height: 16px; border-radius: 999px;
    border: 1px solid var(--border);
  }
  .theme-radio {
    width: 22px; height: 22px; border-radius: 999px;
    border: 2px solid var(--border-strong);
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: transparent;
  }
  .theme-card.selected .theme-radio {
    background: var(--accent);
    border-color: var(--accent);
  }

  /* ── Row inputs ─────────────────────────────────────── */
  .row-input {
    padding: 12px; display: flex; align-items: center; gap: 12px;
    border-bottom: 1px solid var(--border);
  }
  .row-input:last-child { border-bottom: none; }
  .row-icon {
    width: 32px; height: 32px; border-radius: 10px;
    background: var(--surface-2);
    display: flex; align-items: center; justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
  }
  .row-body { flex: 1; min-width: 0; }
  .row-label { font-weight: 700; font-size: 13px; color: var(--ink); margin-bottom: 4px; }
  .text-input {
    width: 100%;
    background: transparent;
    border: none;
    border-bottom: 1px dashed var(--border);
    padding: 2px 0;
    font: inherit;
    font-size: 14px;
    color: var(--ink);
    outline: none;
    user-select: text;
    -webkit-user-select: text;
  }
  .text-input:focus { border-bottom-color: var(--accent); }
  .text-input.token {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    margin-bottom: 10px;
  }
  .goal-input { display: flex; align-items: center; gap: 8px; }
  .goal-input .text-input { width: 60px; }
  .goal-unit { font-size: 13px; color: var(--ink-2); }

  /* ── Furigana radios ───────────────────────────────── */
  .card-label {
    font-size: 12px; font-weight: 700;
    color: var(--ink-2); margin-bottom: 8px;
  }
  .radio-group { display: flex; flex-direction: column; gap: 2px; }
  .radio-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0;
    font-size: 14px; color: var(--ink);
    cursor: pointer;
  }
  .radio-row input[type='radio'] {
    accent-color: var(--accent);
    width: 16px; height: 16px;
    margin: 0;
  }

  .row-toggle {
    display: flex; align-items: center; gap: 12px;
    padding: 8px 4px;
  }
  .row-toggle .row-body { flex: 1; }
  .row-sub { font-size: 12px; color: var(--ink-2); line-height: 1.4; margin-top: 2px; }
  .row-toggle input[type='checkbox'] {
    accent-color: var(--accent);
    width: 20px; height: 20px;
  }

  /* ── Progress card ──────────────────────────────────── */
  .progress-card {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 0;
    padding: 16px 12px;
  }
  .progress-col { text-align: center; padding: 4px 0; }
  .progress-col.bordered { border-left: 1px solid var(--border); border-right: 1px solid var(--border); }
  .progress-val { font-weight: 800; font-size: 20px; color: var(--ink); }
  .progress-val.accent { color: var(--accent); }
  .progress-label {
    font-size: 10px; color: var(--muted);
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em;
    margin-top: 2px;
  }

  /* ── Sync & Reinforce controls ─────────────────────── */
  .kv-row {
    display: flex; justify-content: space-between;
    padding: 6px 0; font-size: 13px;
  }
  .kv-label { color: var(--ink-2); font-weight: 700; }
  .kv-val { color: var(--ink); }
  .kv-val.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }

  .desc { font-size: 13px; color: var(--ink-2); line-height: 1.5; margin: 8px 0; }
  .desc code {
    background: var(--surface-2);
    padding: 0.15em 0.45em;
    border-radius: 6px;
    font-size: 0.92em;
    color: var(--accent);
  }
  .url-hint {
    font-size: 12px; color: var(--muted);
    user-select: all; -webkit-user-select: all;
    margin: 4px 0 10px;
  }

  .btn-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .btn-primary, .btn-danger {
    padding: 10px 16px; border-radius: 12px;
    font-weight: 800; font-size: 13px;
    cursor: pointer; border: none;
  }
  .btn-primary {
    background: var(--gradient-brand);
    color: #fff;
    box-shadow: var(--shadow-sm);
  }
  :global([data-theme='washi']) .btn-primary { color: #2B231A; }
  .btn-danger {
    background: color-mix(in oklab, var(--rose) 14%, var(--surface));
    color: var(--rose);
    border: 1px solid color-mix(in oklab, var(--rose) 50%, transparent);
  }
  .btn-primary:disabled, .btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

  .result {
    margin-top: 8px; padding: 8px 12px;
    border-radius: 10px;
    font-size: 13px;
  }
  .result.ok { background: color-mix(in oklab, var(--mint) 16%, var(--surface)); color: var(--ink); border: 1px solid color-mix(in oklab, var(--mint) 40%, transparent); }
  .result.fail { background: color-mix(in oklab, var(--rose) 14%, var(--surface)); color: var(--ink); border: 1px solid color-mix(in oklab, var(--rose) 40%, transparent); }

  .spinner {
    display: inline-block; width: 12px; height: 12px;
    border: 2px solid currentColor; border-top-color: transparent;
    border-radius: 50%; vertical-align: -2px;
  }
  @media (prefers-reduced-motion: no-preference) {
    .spinner { animation: gentle-spin 0.8s linear infinite; }
  }
  @keyframes gentle-spin { to { transform: rotate(360deg); } }
</style>
