<script setup lang="ts">
/**
 * Where an artifact is filed — its home — chosen from the collections of one axis.
 *
 * One control for all three kinds, because the choice is the same act each time and only the axis
 * differs. It was absent everywhere: the write path has placed and moved artifacts by collection
 * since collections existed and every MCP tool offered it, but nothing a person could reach did, so
 * everything created through the interface landed uncategorised with no way back.
 *
 * The blank option is a real answer, not a prompt: "no collection" is where an artifact sits when it
 * belongs to the repository rather than to a project.
 *
 * **It defaults itself to the collection the reader is browsing.** That is the control's own
 * behaviour rather than each form's, so no form can be the one that forgets it. Only when it has no
 * value yet: an edit form seeds the artifact's own home before the options arrive, and a default
 * that overrode it would offer to move the artifact every time somebody opened the form.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { groupFromQuery } from '../composables/listRequestParams'
import type { GroupList } from '../../domain/schemas/groups'
import { type HomeAxis, defaultHome, homeOptions } from './ArtifactHomeSelect.helpers'

const props = defineProps<{
  modelValue: string
  axis: HomeAxis
  /** Shown on an edit form, where choosing another collection moves the artifact. */
  label?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const groups = ref<GroupList | null>(null)
// Whether the answer has come back, which is not the same as "there are collections": a repository
// with none still has a loaded, empty axis, and the control must stop saying it is loading.
const loaded = ref(false)
const options = computed(() => homeOptions(groups.value, props.axis))

const load = () => {
  loaded.value = false
  Effect.runPromise(svc.listGroups(props.axis))
    .then((list) => {
      groups.value = list
      loaded.value = true
      if (!props.modelValue) {
        emit('update:modelValue', defaultHome(groupFromQuery(route.query.group as string | undefined), options.value))
      }
    })
    .catch(() => { groups.value = null; loaded.value = true })
}

onMounted(load)
watch(() => props.axis, load)
</script>

<template>
  <label class="home-field">
    <span class="home-field__label">{{ label ?? 'Home' }}</span>
    <!--
      Rendered only once the collections are known. A `select` created before its `option` list
      exists has no element matching the value it was given, so the browser resets it to the first
      one — and an edit form then showed "No collection" for an artifact that has one, offering to
      move it out as the effect of saving anything at all.
    -->
    <select
      v-if="loaded"
      class="home-field__select"
      :value="modelValue"
      :disabled="disabled"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">
        No collection
      </option>
      <option
        v-for="entry in options"
        :key="entry.slug"
        :value="entry.slug"
      >
        {{ entry.name }}
      </option>
    </select>
    <select
      v-else
      class="home-field__select"
      disabled
    >
      <option>Loading…</option>
    </select>
  </label>
</template>

<style scoped>
.home-field { display: flex; flex-direction: column; gap: 0.25rem; }
.home-field__label { font-size: 12px; font-weight: 600; color: #374151; }
.home-field__select {
  padding: 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
  color: #111827;
}
.home-field__select:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
