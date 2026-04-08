<script lang="ts">
  import type { Segment } from '../data/types';

  interface Props {
    segments: Segment[];
  }
  const { segments }: Props = $props();
</script>

<span class="furi">
  {#each segments as seg, i (i)}
    {#if seg.r}
      <ruby>{seg.t}<rt>{seg.r}</rt></ruby>
    {:else}
      <span class="plain">{seg.t}</span>
    {/if}
  {/each}
</span>

<style>
  .furi {
    font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif;
    line-height: 2.4;
  }
  ruby {
    ruby-position: over;
  }
  rt {
    font-size: 0.55em;
    color: var(--accent);
    font-weight: 500;
    font-family: 'Hiragino Sans', 'Yu Gothic', system-ui, sans-serif;
    letter-spacing: 0.02em;
  }
  .plain {
    /* nothing — inline */
  }
</style>
