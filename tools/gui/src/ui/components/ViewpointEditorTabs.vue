<script setup lang="ts">
import type { SelectionMode } from '../../domain/viewpointDefinitionDraft'

export type EditorTab = 'general' | 'scope' | 'query' | 'presentation'

/** The editor's tab strip. The INACTIVE selection layer's tab (Scope in query mode,
 * Query in scope mode) stays reachable but is visibly de-emphasized and labeled — its
 * content is kept as history and never executes. */
defineProps<{
  activeTab: EditorTab
  selectionMode: SelectionMode
}>()
const emit = defineEmits<{ 'update:activeTab': [value: EditorTab] }>()
</script>

<template>
  <div class="tabs">
    <button
      :class="{ sel: activeTab === 'general' }"
      @click="emit('update:activeTab', 'general')"
    >
      General
    </button>
    <button
      :class="{ sel: activeTab === 'scope', inactive: selectionMode === 'query' }"
      :title="selectionMode === 'query'
        ? 'Inactive layer — Extended (query) selection is active; kept as history'
        : undefined"
      @click="emit('update:activeTab', 'scope')"
    >
      Scope{{ selectionMode === 'query' ? ' (inactive)' : '' }}
    </button>
    <button
      :class="{ sel: activeTab === 'query', inactive: selectionMode === 'scope' }"
      :title="selectionMode === 'scope'
        ? 'Inactive layer — Simple (scope) selection is active; kept as history'
        : undefined"
      @click="emit('update:activeTab', 'query')"
    >
      Query{{ selectionMode === 'scope' ? ' (inactive)' : '' }}
    </button>
    <button
      :class="{ sel: activeTab === 'presentation' }"
      @click="emit('update:activeTab', 'presentation')"
    >
      Presentation
    </button>
  </div>
</template>

<style scoped>
.tabs { display: flex; gap: 4px; border-bottom: 1px solid #d1d5db; margin: 12px 0; }
.tabs button { appearance: none; border: none; background: none; padding: 8px 14px; font-size: 13px; font-weight: 600; color: #9ca3af; cursor: pointer; border-bottom: 2px solid transparent; }
.tabs button.sel { color: #4338ca; border-color: #6366f1; }
.tabs button.inactive { color: #c4c8cf; font-style: italic; }
.tabs button.inactive.sel { color: #8189a0; border-color: #c4c8cf; }
</style>
