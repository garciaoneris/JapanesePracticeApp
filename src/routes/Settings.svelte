<script lang="ts">
  import { onMount } from 'svelte';
  import { link } from 'svelte-spa-router';
  import { getToken, setToken, clearToken, syncNow, getLastSync, schedulePush } from '../lib/data/sync';
  import { getMeta, putMeta } from '../lib/data/db';

  let token = $state<string | null>(null);
  let tokenInput = $state('');
  let syncing = $state(false);
  let syncResult = $state<{ ok: boolean; error?: string } | null>(null);
  let lastSync = $state<number | null>(null);
  let nativeMode = $state(false);

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
  }

  onMount(async () => {
    await refreshState();
    nativeMode = (await getMeta<boolean>('native-mode')) ?? false;
  });

  async function handleNativeToggle() {
    await putMeta('native-mode', nativeMode);
    schedulePush();
  }

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

<a class="back" href="/" use:link>← Home</a>

<div class="container">
  <h1 class="title">Settings</h1>

  <section class="card">
    <h2 class="section-title">Display Mode</h2>
    <label class="toggle-field">
      <input type="checkbox" bind:checked={nativeMode} onchange={handleNativeToggle} />
      Native mode 🌻
    </label>
    <p class="desc toggle-desc">
      Treat all kanji as mastered. Unlocks all vocabulary and review content.
    </p>
  </section>

  <section class="card">
    <h2 class="section-title">Gist Sync</h2>

    {#if token}
      <div class="field">
        <span class="field-label">Token</span>
        <span class="field-value mono">{maskToken(token)}</span>
      </div>

      <div class="field">
        <span class="field-label">Last synced</span>
        <span class="field-value">{lastSync ? timeAgo(lastSync) : 'Never synced'}</span>
      </div>

      {#if syncResult}
        <div class="result" class:ok={syncResult.ok} class:fail={!syncResult.ok}>
          {#if syncResult.ok}
            Synced successfully.
          {:else}
            Sync failed: {syncResult.error ?? 'unknown error'}
          {/if}
        </div>
      {/if}

      <div class="btn-row">
        <button class="primary" onclick={handleSync} disabled={syncing}>
          {#if syncing}
            <span class="spinner"></span> Syncing...
          {:else}
            Sync now
          {/if}
        </button>
        <button class="danger" onclick={handleRemove} disabled={syncing}>
          Remove token
        </button>
      </div>

    {:else}
      <p class="desc">
        Paste a GitHub Personal Access Token with the <code>gist</code> scope
        to sync your progress across devices.
      </p>
      <p class="url-hint">
        Create a token at github.com/settings/tokens
      </p>

      <input
        type="password"
        class="token-input"
        placeholder="ghp_..."
        bind:value={tokenInput}
        onkeydown={(e) => e.key === 'Enter' && handleSave()}
      />

      <button class="primary save-btn" onclick={handleSave} disabled={!tokenInput.trim()}>
        Save token
      </button>
    {/if}
  </section>
</div>

<style>
  .back {
    display: inline-block;
    padding: 0.75rem 1rem;
    color: var(--fg-dim);
    font-size: 0.9rem;
  }

  .container {
    max-width: 500px;
    margin: 0 auto;
    padding: 0 1rem 3rem;
  }

  .title {
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0.25rem 0 1.25rem;
  }

  .card {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.25rem;
    margin-bottom: 1rem;
  }

  .section-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-dim);
    margin: 0 0 1rem;
    font-weight: 600;
  }

  .desc {
    margin: 0 0 0.5rem;
    color: var(--fg);
    font-size: 0.92rem;
    line-height: 1.5;
  }

  .desc code {
    background: var(--bg-elevated);
    padding: 0.15em 0.45em;
    border-radius: 6px;
    font-size: 0.88em;
    color: var(--accent);
  }

  .url-hint {
    margin: 0 0 1rem;
    color: var(--fg-dim);
    font-size: 0.82rem;
    user-select: all;
    -webkit-user-select: all;
  }

  .token-input {
    display: block;
    width: 100%;
    padding: 0.85rem 1rem;
    font-size: 0.95rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 12px;
    outline: none;
    transition: border-color 0.15s;
  }

  .token-input:focus {
    border-color: var(--accent);
  }

  .token-input::placeholder {
    color: var(--fg-dim);
    opacity: 0.5;
  }

  .save-btn {
    display: block;
    width: 100%;
    margin-top: 0.75rem;
    padding: 0.85rem;
    font-size: 1rem;
  }

  .field {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border-soft);
  }

  .field:last-of-type {
    border-bottom: none;
  }

  .field-label {
    color: var(--fg-dim);
    font-size: 0.88rem;
  }

  .field-value {
    color: var(--fg);
    font-size: 0.88rem;
  }

  .field-value.mono {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    letter-spacing: 0.04em;
  }

  .result {
    margin: 0.75rem 0;
    padding: 0.65rem 0.85rem;
    border-radius: 10px;
    font-size: 0.88rem;
    text-align: center;
  }

  .result.ok {
    background: rgba(94, 202, 124, 0.12);
    border: 1px solid rgba(94, 202, 124, 0.3);
    color: var(--ok);
  }

  .result.fail {
    background: rgba(255, 107, 107, 0.12);
    border: 1px solid rgba(255, 107, 107, 0.3);
    color: var(--err);
  }

  .btn-row {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  .btn-row button {
    flex: 1;
    padding: 0.75rem;
    font-size: 0.95rem;
  }

  .danger {
    background: transparent;
    border: 1px solid var(--err);
    color: var(--err);
  }

  .danger:active:not(:disabled) {
    background: rgba(255, 107, 107, 0.12);
  }

  .spinner {
    display: inline-block;
    width: 0.9em;
    height: 0.9em;
    border: 2px solid rgba(27, 27, 31, 0.3);
    border-top-color: #1b1b1f;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: -0.1em;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .toggle-field {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    font-size: 1rem;
  }

  .toggle-field input[type="checkbox"] {
    width: 1.25rem;
    height: 1.25rem;
    accent-color: var(--accent);
  }

  .toggle-desc {
    margin-top: 0.5rem;
    color: var(--fg-dim);
    font-size: 0.85rem;
  }
</style>
