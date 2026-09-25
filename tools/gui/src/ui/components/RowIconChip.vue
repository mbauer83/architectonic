<script setup lang="ts">
/**
 * The icon a row's instance shows on this diagram, at the row's left edge, and the way to change it.
 * Empty until hovered or focused, so an untouched diagram's list looks as it always did; with an icon
 * set, the picture, and in its title where it comes from.
 */
import { computed, inject } from 'vue'
import { diagramIconsKey } from '../composables/useDiagramIcons'

const props = defineProps<{ instanceId: string; elementName: string; open: boolean }>()
const emit = defineEmits<{ toggle: [] }>()

const icons = inject(diagramIconsKey)!
const LEVEL_CAPTION = {
  instance: 'this element', type: 'all of its type here', 'specialization-default': 'its specialization',
} as const
const shown = computed(() => icons.shownFor(props.instanceId))
const title = computed(() =>
  shown.value ? `Icon from ${LEVEL_CAPTION[shown.value.icon.level]}; change it` : 'Give this element an icon')
</script>

<template>
  <button
    class="icon-chip"
    :class="{ 'icon-chip--set': shown, expanded: open }"
    :title="title"
    :aria-label="`Icon for ${elementName}`"
    :aria-expanded="open"
    @click="emit('toggle')"
  >
    <img
      v-if="shown"
      :src="shown.picture"
      alt=""
    >
  </button>
</template>

<style scoped>
.icon-chip {
  width: 22px; height: 22px; border-radius: 5px; flex-shrink: 0; padding: 1px; cursor: pointer;
  border: 1px dashed transparent; background: none; display: inline-flex; align-items: center; justify-content: center;
}
:global(.entity-row:hover) .icon-chip, .icon-chip:focus-visible, .icon-chip.expanded { border-color: #c4b5fd; }
.icon-chip--set { border-style: solid; border-color: #ede9fe; }
.icon-chip img { width: 18px; height: 18px; object-fit: contain; }
</style>
