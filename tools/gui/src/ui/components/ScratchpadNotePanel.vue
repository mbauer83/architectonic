<script setup lang="ts">
/**
 * What a selected note may become, and what a drawn link's verdict means.
 *
 * The refinement ladder is the meta-ontology's own: domain, then entity type, then specialization.
 * `useEntityFilters` already groups the ontology's types by domain and fetches them once, so this
 * reuses it rather than adding a second source — the picker's two levels *are* those two levels.
 *
 * Nothing here is required. A note that stays undecided has done its job; the panel offers, and
 * says so.
 */
import { computed } from 'vue'
import { useEntityFilters } from '../composables/useEntityFilters'
import type { Link, Note } from '../../domain/schemas/scratchpads'

const props = defineProps<{ note: Note | null; links: readonly Link[] }>()
const emit = defineEmits<{
  (event: 'type-note', payload: { id: string; elementType: string }): void
  (event: 'untype-note', payload: { id: string }): void
  (event: 'forget-note', payload: { id: string }): void
  (event: 'reverse-link', payload: { id: string }): void
  (event: 'type-link', payload: { id: string; connectionType: string }): void
}>()

const { selectedDomains, domainOptions, availableEntityTypes } = useEntityFilters()

/** A note tied to the model takes its type from there, so the picker steps aside rather than
 * offering a change the aggregate would refuse. */
const boundOrRealized = computed(() => props.note?.['model-ref'] ?? null)
const isBound = computed(() => boundOrRealized.value?.kind === 'bound')

const links = computed(() =>
  props.note ? props.links.filter((link) => link.source === props.note!.id || link.target === props.note!.id) : [],
)
/** Links worth showing: one that says nothing needs no row. */
const notable = computed(() => links.value.filter((link) => (link.verdict?.kind ?? 'unverified') !== 'unverified'))
</script>

<template>
  <aside
    v-if="note"
    class="panel"
    data-testid="note-panel"
  >
    <h2 class="title">
      {{ note.title }}
    </h2>

    <p
      v-if="boundOrRealized"
      class="tied"
      data-testid="note-tied"
    >
      {{ isBound ? 'Bound to' : 'Realized as' }}
      <code>{{ boundOrRealized['artifact-id'] }}</code>
      <button
        type="button"
        data-testid="note-release"
        @click="isBound
          ? emit('untype-note', { id: note.id })
          : emit('forget-note', { id: note.id })"
      >
        {{ isBound ? 'Unbind' : 'Forget' }}
      </button>
    </p>

    <template v-else>
      <p class="hint">
        Nothing here needs a type. Narrow it when you know, one level at a time.
      </p>
      <label class="field">
        <span>Domain</span>
        <select
          :value="selectedDomains[0] ?? ''"
          data-testid="type-domain"
          @change="selectedDomains = ($event.target as HTMLSelectElement).value
            ? [($event.target as HTMLSelectElement).value] : []"
        >
          <option value="">
            Any
          </option>
          <option
            v-for="option in domainOptions"
            :key="option.key"
            :value="option.key"
          >
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="field">
        <span>Element type</span>
        <select
          :value="note['element-type'] ?? ''"
          data-testid="type-element"
          @change="($event.target as HTMLSelectElement).value
            ? emit('type-note', { id: note.id, elementType: ($event.target as HTMLSelectElement).value })
            : emit('untype-note', { id: note.id })"
        >
          <option value="">
            Undecided
          </option>
          <option
            v-for="value in availableEntityTypes"
            :key="value"
            :value="value"
          >
            {{ value }}
          </option>
        </select>
      </label>
    </template>

    <section
      v-if="notable.length"
      class="verdicts"
      data-testid="link-verdicts"
    >
      <h3>Links</h3>
      <p
        v-for="link in notable"
        :key="link.id"
        class="verdict"
        :class="link.verdict?.kind"
        :data-verdict-for="link.id"
      >
        <span class="msg">{{ link.verdict?.message }}</span>
        <!-- Leads the remedies, deliberately: dragging an ordered triple the wrong way is the
             commonest slip there is, and one click is almost certainly what was meant. -->
        <button
          v-if="link.verdict?.['reverse-permitted']"
          type="button"
          class="primary"
          :data-reverse-link="link.id"
          @click="emit('reverse-link', { id: link.id })"
        >
          Reverse the link
        </button>
        <button
          v-for="option in link.verdict?.alternatives ?? []"
          :key="option"
          type="button"
          :data-link-type="option"
          @click="emit('type-link', { id: link.id, connectionType: option })"
        >
          {{ option }}
        </button>
      </p>
    </section>
  </aside>
</template>

<style scoped>
.panel {
  position: absolute; top: 14px; left: 14px; width: 300px; z-index: 4;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px;
  box-shadow: 0 4px 14px rgba(0,0,0,.08); font-size: 12.5px;
}
.title { font-size: 13.5px; margin: 0 0 8px; font-weight: 600; }
.hint { color: #6b7280; margin: 0 0 10px; font-size: 11.5px; }
.tied { margin: 0; color: #059669; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tied code { font-size: 11px; color: #374151; word-break: break-all; }
.tied button, .verdict button {
  padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px; background: #fff;
  font-size: 11px; cursor: pointer; color: #374151;
}
.verdict button.primary { border-color: #2563eb; color: #2563eb; font-weight: 600; }
.field { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.field span { color: #6b7280; }
.field select { flex: 1; padding: 4px 6px; border: 1px solid #d1d5db; border-radius: 5px; font-size: 12px; }
.verdicts { border-top: 1px solid #f0f0f2; margin-top: 10px; padding-top: 8px; }
.verdicts h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 6px; }
.verdict { margin: 0 0 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.verdict .msg { flex: 1 1 100%; color: #6b7280; font-size: 11.5px; }
.verdict.refused .msg { color: #dc2626; }
.verdict.narrowed .msg { color: #d97706; }
.verdict.permitted .msg { color: #059669; }
</style>
