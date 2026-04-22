<script lang="ts">
  // Disabled for iPad perf: this used to render 8–12 continuously-drifting
  // petal SVGs on every hero card. The drift was cheap on desktop but
  // compounded into noticeable jank on iPad when combined with the grid
  // and shimmer layers. Kept as an empty component so every call site
  // can keep its current markup unchanged — there's nothing to render.
  interface Props {
    count?: number;
  }
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  let { count = 8 }: Props = $props();
  void count;
</script>
