<script setup lang="ts">
/**
 * The icon a row's instance shows on this diagram, at the row's left edge, and the way to change it.
 * Without an icon it shows a faint placeholder, strengthened when the row is hovered, so the way in is
 * findable without crowding a list nobody is giving icons; with one, the picture, and in its title
 * where it comes from.
 */
import { computed, inject, watchEffect } from 'vue'
import { diagramIconsKey } from '../composables/useDiagramIcons'

const props = defineProps<{
  instanceId: string
  elementName: string
  open: boolean
  /** The model entity it draws, where it draws one. */
  entityId?: string
  /** The type the diagram draws it as, where the notation has types of its own. */
}>()
const emit = defineEmits<{ toggle: [] }>()

const icons = inject(diagramIconsKey)!
// Asked about while shown: the preview answers for the instances rows show, and only those.
watchEffect((onCleanup) => {
  onCleanup(icons.register({
    instance_id: props.instanceId,
    ...(props.entityId ? { entity_id: props.entityId } : {}),
  }))
})
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
    <svg
      v-else
      class="icon-chip__placeholder"
      viewBox="0 0 16 16"
      width="14"
      height="14"
      aria-hidden="true"
    >
      <path
        d="M3 3h7M1.5 4.5v6A1.5 1.5 0 0 0 3 12h7a1.5 1.5 0 0 0 1.5-1.5V8
           M3.5 10.5 6 7.5l2 2 1.2-1.3 1.8 2.3M13 1.5v4M11 3.5h4"
      />
    </svg>
  </button>
</template>

<style scoped>
.icon-chip {
  width: 22px; height: 22px; border-radius: 5px; flex-shrink: 0; padding: 1px; cursor: pointer;
  border: 1px dashed #e5e7eb; background: none; color: #9ca3af;
  display: inline-flex; align-items: center; justify-content: center;
}
.icon-chip__placeholder {
  opacity: .55; fill: none; stroke: currentColor; stroke-width: 1.2; stroke-linecap: round; stroke-linejoin: round;
}
.icon-chip:hover, .icon-chip:focus-visible, .icon-chip.expanded { border-color: #a78bfa; color: #6d28d9; }
.icon-chip:hover .icon-chip__placeholder, .icon-chip:focus-visible .icon-chip__placeholder,
.icon-chip.expanded .icon-chip__placeholder { opacity: 1; }
.icon-chip--set { border-style: solid; border-color: #ede9fe; }
.icon-chip img { width: 18px; height: 18px; object-fit: contain; }
</style>
