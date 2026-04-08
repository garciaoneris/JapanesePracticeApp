<script lang="ts">
  import Router from 'svelte-spa-router';
  import Home from './routes/Home.svelte';
  import Learn from './routes/Learn.svelte';
  import Vocab from './routes/Vocab.svelte';
  import Review from './routes/Review.svelte';
  import NotFound from './routes/NotFound.svelte';
  import { onMount } from 'svelte';
  import { ensureBundleLoaded } from './lib/data/bundle';

  const routes = {
    '/': Home,
    '/learn/:char': Learn,
    '/vocab/:id': Vocab,
    '/review': Review,
    '*': NotFound,
  };

  let loading = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      await ensureBundleLoaded();
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
    color: var(--fg-dim);
  }
  .err { color: var(--err); }
</style>
