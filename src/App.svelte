<script lang="ts">
  import Router from 'svelte-spa-router';
  import Home from './routes/Home.svelte';
  import Learn from './routes/Learn.svelte';
  import Vocab from './routes/Vocab.svelte';
  import Vocabulary from './routes/Vocabulary.svelte';
  import Review from './routes/Review.svelte';
  import Reinforce from './routes/Reinforce.svelte';
  import FillKanji from './routes/FillKanji.svelte';
  import Settings from './routes/Settings.svelte';
  import Complete from './routes/Complete.svelte';
  import NotFound from './routes/NotFound.svelte';
  import { onMount } from 'svelte';
  import { ensureBundleLoaded } from './lib/data/bundle';
  import { syncNow, getToken } from './lib/data/sync';
  import { loadFuriganaMode } from './lib/data/furiganaMode';
  import { getMeta } from './lib/data/db';

  type Theme = 'washi' | 'neon' | 'sakura';
  const VALID_THEMES: readonly Theme[] = ['washi', 'neon', 'sakura'];

  /** Read persisted theme and apply to <html> before any route renders so
   *  first paint uses the correct palette (no flash of default). */
  async function applyTheme(): Promise<void> {
    const stored = await getMeta<string>('theme');
    const theme: Theme = VALID_THEMES.includes(stored as Theme) ? (stored as Theme) : 'washi';
    document.documentElement.setAttribute('data-theme', theme);
  }

  const routes = {
    '/': Home,
    '/vocabulary': Vocabulary,
    '/learn/:char': Learn,
    '/vocab/:id': Vocab,
    '/review': Review,
    '/fill-kanji': FillKanji,
    '/complete': Complete,
    '/settings': Settings,
    '/reinforce': Reinforce,
    '*': NotFound,
  };

  let loading = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      // Theme first so the loading-spinner flash uses the right palette.
      await applyTheme();
      await ensureBundleLoaded();
      // Prime the furigana-mode cache before any Furigana instance mounts.
      await loadFuriganaMode();
      // Background sync on startup if a token is configured.
      getToken().then((t) => { if (t) syncNow().catch(() => {}); });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });
</script>

{#if loading}
  <div class="center">Loading dictionary…</div>
{:else if error}
  <div class="center err">Failed to load bundle: {error}</div>
{:else}
  <Router {routes} />
{/if}

<style>
  .center {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-size: 1.1rem;
    color: var(--muted);
  }
  .err { color: var(--rose); }
</style>
