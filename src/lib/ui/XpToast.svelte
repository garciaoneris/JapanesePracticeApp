<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { onXpGain } from '../gamification/xpToast';
  import Blossom from './Blossom.svelte';

  interface Chip { id: number; amount: number; }

  let chips = $state<Chip[]>([]);
  let nextId = 0;
  let unsubscribe: (() => void) | null = null;

  onMount(() => {
    unsubscribe = onXpGain((amount) => {
      const id = nextId++;
      chips = [...chips, { id, amount }];
      // Animation is 1.6s; remove just after it ends so chips don't pile
      // up in the DOM.
      setTimeout(() => {
        chips = chips.filter((c) => c.id !== id);
      }, 1700);
    });
  });

  onDestroy(() => {
    unsubscribe?.();
  });
</script>

<div class="xp-toast-root" aria-live="polite" aria-atomic="true">
  {#each chips as c (c.id)}
    <div class="xp-chip">
      <span class="bloom" aria-hidden="true"><Blossom size={14} /></span>
      +{c.amount} XP
    </div>
  {/each}
</div>

<style>
  .xp-toast-root {
    position: fixed;
    right: 24px;
    bottom: 28px;
    display: flex;
    flex-direction: column-reverse;
    gap: 6px;
    pointer-events: none;
    z-index: 9999;
  }
  .xp-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--gradient-brand);
    color: #fff;
    font-weight: 800;
    font-size: 14px;
    letter-spacing: 0.02em;
    font-variant-numeric: tabular-nums;
    box-shadow: var(--shadow-md);
    /* Float-up + fade animation. `both` keeps the chip at the final
       state until the JS removes it. */
    animation: xp-fly 1.6s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  :global([data-theme='washi']) .xp-chip { color: #2B231A; }
  .bloom { color: #fff; display: inline-flex; }
  :global([data-theme='washi']) .bloom { color: #fff; }

  @keyframes xp-fly {
    0%   { opacity: 0; transform: translateY(24px) scale(0.85); }
    12%  { opacity: 1; transform: translateY(0)    scale(1); }
    75%  { opacity: 1; transform: translateY(-36px) scale(1); }
    100% { opacity: 0; transform: translateY(-72px) scale(0.95); }
  }
</style>
