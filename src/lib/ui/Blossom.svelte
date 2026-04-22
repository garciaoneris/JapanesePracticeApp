<script lang="ts">
  interface Props {
    size?: number;
  }
  let { size = 22 }: Props = $props();
</script>

<svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
  <ellipse cx="20" cy="10" rx="6" ry="9" fill="currentColor" opacity="0.85" transform="rotate(0 20 20)"/>
  <ellipse cx="20" cy="10" rx="6" ry="9" fill="currentColor" opacity="0.85" transform="rotate(72 20 20)"/>
  <ellipse cx="20" cy="10" rx="6" ry="9" fill="currentColor" opacity="0.85" transform="rotate(144 20 20)"/>
  <ellipse cx="20" cy="10" rx="6" ry="9" fill="currentColor" opacity="0.85" transform="rotate(216 20 20)"/>
  <ellipse cx="20" cy="10" rx="6" ry="9" fill="currentColor" opacity="0.85" transform="rotate(288 20 20)"/>
  <circle cx="20" cy="20" r="3" fill="var(--accent-2, #F2B138)"/>
</svg>

<style>
  svg {
    display: inline-block;
    vertical-align: middle;
  }
</style>
