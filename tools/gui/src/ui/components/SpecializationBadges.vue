<script setup lang="ts">
/**
 * One «badge» per applied specialization, in declaration order.
 *
 * A concept may carry several (ArchiMate §15.2), so this renders a list rather than a value — the
 * surfaces that showed only the first had no way to say there were others. Lifted out of
 * `EntitiesView.vue`, which is at its recorded length limit and cannot take the five lines the
 * `v-for` needs; the badge and its one style rule are self-contained, which is what makes it liftable
 * rather than a split for the sake of a number.
 *
 * `ConnectionsPanel` and `EntityDetailHeader` render their own: the first is styled elsewhere and the
 * second interleaves a separator between badges. Folding either in here would change how it looks.
 */
defineProps<{ specializations: readonly string[] }>()
</script>

<template>
  <span
    v-for="spec in specializations"
    :key="spec"
    class="type-specialization"
  >«{{ spec }}»</span>
</template>

<style scoped>
.type-specialization { font-size: 11px; font-style: italic; color: #6d28d9; }
</style>
