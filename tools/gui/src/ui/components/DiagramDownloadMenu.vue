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
 *
 * A surface showing an ad-hoc reading passes its lens, and the download then exports *that* picture.
 * The lens travels as the same query parameters the display asked for, so the export is not a second
 * rendering that agrees today — it is the same render, requested as an attachment.
 */
import DownloadMenu from './DownloadMenu.vue'
import { EMPTY_READING_LENS, lensParams, type ReadingLens } from '../../domain/readingLens'

const props = withDefaults(defineProps<{ diagramId: string; lens?: ReadingLens }>(), {
  lens: () => EMPTY_READING_LENS,
})

const download = (format: 'png' | 'svg') => {
  const params = new URLSearchParams({ format })
  for (const [key, value] of Object.entries(lensParams(props.lens) ?? {})) {
    if (Array.isArray(value)) value.forEach((member: string) => params.append(key, member))
    else if (value !== '') params.set(key, value as string)
  }
  window.location.href =
    `/api/diagrams/${encodeURIComponent(props.diagramId)}/download?${params.toString()}`
}
</script>

<template>
  <DownloadMenu @select="download" />
</template>
