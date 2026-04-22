<script lang="ts">
  interface Props {
    size?: number;
  }
  let { size = 22 }: Props = $props();
  // Unique gradient id per instance to avoid SVG defs collisions when
  // multiple flames render on the same page.
  const gid = `flame-g-${Math.random().toString(36).slice(2, 9)}`;
</script>

<svg width={size} height={size * 1.1} viewBox="0 0 24 26" aria-hidden="true">
  <defs>
    <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#FFB546"/>
      <stop offset="0.6" stop-color="#FF6A3D"/>
      <stop offset="1" stop-color="#E6453C"/>
    </linearGradient>
  </defs>
  <path
    d="M12 1c2 3 5 5 6 9 1 4-1 8-2 10 2-1 3-3 3-5 1 4-2 8-5 10-4 2-9 0-10-4-1-3 0-6 1-8 2-3 3-5 3-8 0-1 0-2 1-3 1 1 2 0 3-1z"
    fill={`url(#${gid})`}
  />
  <path
    d="M12 10c1 2 3 3 3 6 0 3-2 5-4 5-2 0-3-2-3-4 0-2 2-4 4-7z"
    fill="#FFE37A"
    opacity="0.85"
  />
</svg>

<style>
  svg {
    display: inline-block;
    vertical-align: middle;
  }
</style>
