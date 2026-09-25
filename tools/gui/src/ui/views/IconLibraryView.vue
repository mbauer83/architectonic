<script setup lang="ts">
/**
 * The icon library, for curation: what it holds, adding to it, and editing, retiring, replacing and
 * deleting what this repository owns. Icons are given to elements in the diagram editor, not here.
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { modelServiceKey } from '../keys'
import type { IconList, IconSummary } from '../../domain/schemas/icons'
import type { RepoError } from '../../ports/repositoryErrors'
import { useQuery } from '../composables/useQuery'
import IconLibraryAddForm from '../components/IconLibraryAddForm.vue'
import IconLibraryCard from '../components/IconLibraryCard.vue'

const svc = inject(modelServiceKey)!
const library = useQuery<IconList, RepoError>()
const icons = computed(() => library.data.value?.items ?? [])
const error = library.errorMessage
const query = ref('')
const includeRetired = ref(false)
const adding = ref(false)

const load = (): void =>
  library.run(svc.listIcons({ q: query.value || undefined, include_retired: includeRetired.value }))
onMounted(load)
watch([query, includeRetired], load)

const active = computed(() => icons.value.filter((icon) => icon.status === 'active'))
const othersThan = (icon: IconSummary): readonly IconSummary[] =>
  active.value.filter((other) => other.artifact_id !== icon.artifact_id)
const added = (): void => {
  adding.value = false
  load()
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>Icons</h1>
      <input
        v-model="query"
        type="search"
        placeholder="Search by name or attribution"
        aria-label="Search the library"
      >
      <label class="retired"><input
        v-model="includeRetired"
        type="checkbox"
      > Show retired</label>
      <button
        class="primary"
        @click="adding = !adding"
      >
        Add to the library…
      </button>
    </header>

    <IconLibraryAddForm
      v-if="adding"
      @added="added"
      @cancel="adding = false"
    />

    <p
      v-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-else-if="!icons.length"
      class="empty"
    >
      The library holds no icons yet. Add one here, or upload one for a diagram from its editor.
    </p>
    <div class="grid">
      <IconLibraryCard
        v-for="icon in icons"
        :key="icon.artifact_id"
        :icon="icon"
        :others="othersThan(icon)"
        @changed="load"
      />
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 24px 16px; display: flex; flex-direction: column; gap: 14px; }
.page-head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.page-head h1 { margin: 0 12px 0 0; font-size: 22px; }
.page-head input[type=search] {
  flex: 1; min-width: 200px; padding: 6px 10px;
  border: 1px solid #e5e7eb; border-radius: 6px;
}
.retired { font-size: 13px; color: #374151; }
.primary { padding: 6px 12px; border-radius: 6px; border: none; background: #2563eb; color: #fff; cursor: pointer; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.error { color: #dc2626; }
.empty { color: #6b7280; }
</style>
