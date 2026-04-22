<script lang="ts">
  interface Props {
    size?: number;
    color?: string;
  }
  let { size = 14, color = 'currentColor' }: Props = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
  <path d="M12 2c2 3 4 5 6 6.5-2 1-4 1-6 1s-4 0-6-1c2-1.5 4-3.5 6-6.5z" fill={color}/>
  <path d="M22 12c-3 2-5 4-6.5 6-1-2-1-4-1-6s0-4 1-6c1.5 2 3.5 4 6.5 6z" fill={color} opacity="0.88"/>
  <path d="M12 22c-2-3-4-5-6-6.5 2-1 4-1 6-1s4 0 6 1c-2 1.5-4 3.5-6 6.5z" fill={color} opacity="0.76"/>
  <path d="M2 12c3-2 5-4 6.5-6 1 2 1 4 1 6s0 4-1 6c-1.5-2-3.5-4-6.5-6z" fill={color} opacity="0.64"/>
  <circle cx="12" cy="12" r="1.8" fill={color} opacity="0.5"/>
</svg>

<style>
  svg {
    display: inline-block;
    vertical-align: middle;
  }
</style>
