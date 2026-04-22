<script lang="ts">
  // Disabled for iPad perf: this used to drop 26 rotating confetti pieces
  // continuously on the Complete screen. Kept as an empty component so
  // Complete.svelte can keep its `<Confetti />` tag unchanged.
  interface Props {
    count?: number;
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  let { count = 26 }: Props = $props();
  void count;
</script>
