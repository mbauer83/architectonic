<script setup lang="ts">
/**
 * The download menu, integrated for a persisted diagram: it knows where a diagram's bytes live.
 *
 * The split is between what the affordance *is* — a ↓ that unfolds into the formats on offer,
 * which `DownloadMenu` owns and any surface can mount — and what downloading *means here*, which
 * differs per surface and is configuration. Two surfaces offer a persisted diagram's download, so
 * that meaning is stated once, here, and they pass an id rather than each repeating a handler and
 * an address. The graph explorer mounts the plain menu directly: its meaning has one caller, and a
 * wrapper for one caller is ceremony.
 */
import DownloadMenu from './DownloadMenu.vue'

const props = defineProps<{ diagramId: string }>()

const download = (format: 'png' | 'svg') => {
  window.location.href =
    `/api/diagrams/${encodeURIComponent(props.diagramId)}/download?format=${format}`
}
</script>

<template>
  <DownloadMenu @select="download" />
</template>
