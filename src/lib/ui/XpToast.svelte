<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { onXpGain } from '../gamification/xpToast';
  import Blossom from './Blossom.svelte';

  interface Chip { id: number; amount: number; x: number; y: number; }

  let chips = $state<Chip[]>([]);
  let nextId = 0;
  let unsubscribe: (() => void) | null = null;

  onMount(() => {
    unsubscribe = onXpGain((amount, pointer) => {
      const id = nextId++;
      // Anchor the chip to the last tap so the reward clearly belongs
      // to the action that earned it. Sanity-clamp so a tap near the
      // viewport edge still keeps the chip on-screen during its
      // float-up animation.
      const x = Math.max(72, Math.min(window.innerWidth - 72, pointer.x));
      const y = Math.max(80, Math.min(window.innerHeight - 20, pointer.y));
      chips = [...chips, { id, amount, x, y }];
      // Animation is 1.6s; remove just after it ends so chips don't
      // pile up in the DOM.
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
    <div class="xp-chip" style="left: {c.x}px; top: {c.y}px;">
      <span class="bloom" aria-hidden="true"><Blossom size={14} /></span>
      +{c.amount} XP
    </div>
  {/each}
</div>

<style>
  .xp-toast-root {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 9999;
  }
  .xp-chip {
    position: absolute;
    /* Chip origin is the anchor point; translate so the chip sits
       slightly above the tap and horizontally centered on it. */
    transform: translate(-50%, -120%);
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
    white-space: nowrap;
    /* Float-up + fade animation. `both` keeps the chip at the final
       state until the JS removes it. */
    animation: xp-fly 1.6s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  :global([data-theme='washi']) .xp-chip { color: #2B231A; }
  .bloom { color: #fff; display: inline-flex; }
  :global([data-theme='washi']) .bloom { color: #fff; }

  @keyframes xp-fly {
    0%   { opacity: 0; transform: translate(-50%, -60%)  scale(0.85); }
    12%  { opacity: 1; transform: translate(-50%, -120%) scale(1); }
    75%  { opacity: 1; transform: translate(-50%, -240%) scale(1); }
    100% { opacity: 0; transform: translate(-50%, -320%) scale(0.95); }
  }
</style>
