<script lang="ts">
  import { link } from 'svelte-spa-router';
</script>

<div class="wrap">
  <h1>404</h1>
  <p>No route matches.</p>
  <a href="/" use:link>Home</a>
</div>

<style>
  .wrap {
    padding: 3rem 1rem;
    text-align: center;
    color: var(--fg-dim);
  }
  h1 { font-size: 3rem; margin: 0; }
</style>
