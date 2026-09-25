<script setup lang="ts">
/**
 * Choose the icon an element shows on this diagram: from the library, or uploaded for this diagram.
 *
 * Opened from a row, so it knows the element and its type and offers the two scopes the diagram can
 * state — this element, or every element of its type here. The library is asked for what applies to
 * the element, so an icon restricted to another type is never offered. What the choice then shows is
 * the server's to say; the picker only states the choice.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { IconStyle, IconSummary } from '../../domain/schemas/icons'
import type { IconScope, IconStatement, IconUploadForDiagram } from '../lib/diagramIcons'
import { ICON_FILE_TYPES, iconUploadFromFile } from '../lib/iconFiles'

const props = defineProps<{
  /** What the picker is for, in the reader's words: the element's name. */
  elementName: string
  /** Its type's name, the key a type-wide statement is made under. */
  typeName: string
  /** Asked of the library: an entity id or a type name. */
  applicableTo: string
  /** The styles this diagram type draws; the toggle offers only these. */
  styles: readonly IconStyle[]
  /** What the diagram states at each scope now, so *Clear* says what it clears. */
  current: Partial<Record<IconScope, IconStatement>>
}>()

const emit = defineEmits<{
  choose: [scope: IconScope, statement: IconStatement | null]
  upload: [scope: IconScope, upload: IconUploadForDiagram, style: IconStyle | undefined]
  close: []
}>()

const svc = inject(modelServiceKey)!
const scope = ref<IconScope>(props.current.instance || !props.current.type ? 'instance' : 'type')
const style = ref<IconStyle | undefined>(props.current[scope.value]?.style)
const query = ref('')
const icons = ref<readonly IconSummary[]>([])
const loadError = ref<string | null>(null)

const load = async (): Promise<void> => {
  const asked = { applicable_to: props.applicableTo, q: query.value || undefined }
  const exit = await Effect.runPromiseExit(svc.listIcons(asked))
  if (Exit.isSuccess(exit)) {
    icons.value = exit.value.items
    loadError.value = null
  } else {
    loadError.value = 'The library could not be read'
  }
}
onMounted(load)
watch(query, load)

const stated = computed(() => props.current[scope.value])
const choose = (icon: string): void =>
  emit('choose', scope.value, { icon, ...(style.value ? { style: style.value } : {}) })

const uploadError = ref<string | null>(null)

const onFile = async (event: Event): Promise<void> => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const upload = await iconUploadFromFile(file)
  if ('refused' in upload) {
    uploadError.value = upload.refused
    return
  }
  emit('upload', scope.value, upload, style.value)
}
</script>

<template>
  <div
    class="icon-picker"
    role="dialog"
    :aria-label="`Icon for ${elementName}`"
    @keydown.esc="emit('close')"
  >
    <div class="ip-head">
      <div
        class="ip-scope"
        role="radiogroup"
        aria-label="Where the icon is stated"
      >
        <label><input
          v-model="scope"
          type="radio"
          value="instance"
        > This element</label>
        <label><input
          v-model="scope"
          type="radio"
          value="type"
        > All {{ typeName }} here</label>
      </div>
      <button
        class="ip-close"
        aria-label="Close"
        @click="emit('close')"
      >
        ×
      </button>
    </div>

    <div
      v-if="styles.length > 1"
      class="ip-style"
      role="radiogroup"
      aria-label="How the icon is drawn"
    >
      <label><input
        v-model="style"
        type="radio"
        :value="undefined"
      > Icon's own</label>
      <label
        v-for="option in styles"
        :key="option"
      ><input
        v-model="style"
        type="radio"
        :value="option"
      > {{ option === 'badge' ? 'Badge' : 'Figure' }}</label>
    </div>

    <input
      v-model="query"
      class="ip-search"
      type="search"
      placeholder="Search the library"
      aria-label="Search the library"
    >
    <div
      v-if="loadError"
      class="ip-err"
    >
      {{ loadError }}
    </div>
    <ul class="ip-list">
      <li
        v-for="icon in icons"
        :key="icon.artifact_id"
      >
        <button
          class="ip-entry"
          :class="{ 'ip-entry--stated': stated?.icon === icon.artifact_id }"
          :title="icon.attribution"
          @click="choose(icon.artifact_id)"
        >
          <img
            :src="svc.iconImageUrl(icon.artifact_id)"
            alt=""
            width="24"
            height="24"
          >
          <span class="ip-name">{{ icon.name }}</span>
        </button>
      </li>
      <li
        v-if="!icons.length && !loadError"
        class="ip-empty"
      >
        No icon in the library applies to this element
      </li>
    </ul>

    <div class="ip-actions">
      <label class="ip-upload">
        Upload for this diagram…
        <input
          type="file"
          :accept="ICON_FILE_TYPES"
          @change="onFile"
        >
      </label>
      <button
        v-if="stated"
        class="ip-clear"
        @click="emit('choose', scope, null)"
      >
        Clear
      </button>
    </div>
    <div
      v-if="uploadError"
      class="ip-err"
    >
      {{ uploadError }}
    </div>
  </div>
</template>

<style scoped>
.icon-picker {
  display: flex; flex-direction: column; gap: 8px; padding: 10px; margin: 0 10px 8px;
  border: 1px solid #ddd6fe; border-radius: 8px; background: #faf5ff; font-size: 12px;
}
.ip-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.ip-scope, .ip-style { display: flex; flex-wrap: wrap; gap: 10px; color: #374151; }
.ip-close { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 16px; line-height: 1; }
.ip-search { padding: 5px 8px; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 12px; }
.ip-list {
  list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px;
  max-height: 180px; overflow-y: auto;
}
.ip-entry {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 4px 6px; border: 1px solid transparent;
  border-radius: 6px; background: #fff; cursor: pointer; text-align: left;
}
.ip-entry:hover { border-color: #ddd6fe; }
.ip-entry--stated { border-color: #7c3aed; }
.ip-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #1f2937; }
.ip-empty { color: #9ca3af; padding: 4px 2px; }
.ip-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ip-upload { color: #6d28d9; cursor: pointer; font-weight: 600; }
.ip-upload input { display: none; }
.ip-clear {
  border: 1px solid #fecaca; background: #fff; color: #dc2626; border-radius: 5px; padding: 2px 8px; cursor: pointer;
}
.ip-err { color: #dc2626; }
</style>
