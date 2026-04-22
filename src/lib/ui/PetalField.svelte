<script lang="ts">
  import Petal from './Petal.svelte';

  interface Props {
    count?: number;
  }
  let { count = 8 }: Props = $props();

  // Deterministic layout — same seed each render so HMR doesn't reshuffle
  // particles mid-session. Durations + delays roughly match the prototype.
  const petals = Array.from({ length: count }, (_, i) => ({
    left: `${(i * 13 + 7) % 95}%`,
    size: 10 + (i % 4) * 4,
    duration: 12 + (i % 5) * 3,
    delay: -(i * 2),
  }));
</script>

<div class="petal-field" aria-hidden="true">
  {#each petals as p, i (i)}
    <div
      class="p"
      style="left: {p.left}; animation-duration: {p.duration}s; animation-delay: {p.delay}s;"
    >
      <Petal size={p.size} />
    </div>
  {/each}
</div>

<style>
  .petal-field {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
  }
  .p {
    position: absolute;
    top: -5%;
    color: var(--petal);
    opacity: 0.28;
  }
  :global([data-theme='neon']) .p {
    opacity: 0.55;
    /* `filter: blur + drop-shadow` dropped — on iPad that filter
       pass per petal (per compositor frame) was the main source of
       Neon-only jank. The petals still read as pink against the
       dark bg via their accent color. */
  }
  @media (prefers-reduced-motion: no-preference) {
    .p {
      animation-name: petal-drift;
      animation-timing-function: linear;
      animation-iteration-count: infinite;
    }
  }
</style>
