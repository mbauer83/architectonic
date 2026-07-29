<script setup lang="ts">
/**
 * "Scope" tab of the viewpoint definition editor: entity and connection type
 * admissibility, each with three modes — include all types, include only selected types,
 * or exclude selected types from an otherwise-unrestricted scope. Entity types are
 * grouped by domain (their `hierarchy[0]`) with a domain-level bulk action; connection
 * types have no such grouping and are picked from one flat, searchable list. Standard
 * modelValue/update:modelValue two-way binding, same convention as CriteriaTreeBuilder —
 * the parent v-models this onto its own `draft.scope`.
 */
import { computed, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type { ScopeDraft } from '../../domain/viewpointDefinitionDraft'
import {
  type ScopeMode,
  carveOutFromDomainExclusion,
  connectionScopeMode,
  entityExclusionState,
  entityScopeMode,
  excludeDomain,
  excludeDomainFromIncludeList,
  filterByQuery,
  groupByDomain,
  includeDomain,
  reincludeDomain,
  toggleInList,
  withConnectionScopeMode,
  withEntityScopeMode,
} from './ViewpointScopeTab.helpers'

const props = defineProps<{
  modelValue: ScopeDraft
  catalog: CriteriaCatalog
}>()
const emit = defineEmits<{ 'update:modelValue': [value: ScopeDraft] }>()

const update = (patch: Partial<ScopeDraft>) => emit('update:modelValue', { ...props.modelValue, ...patch })

const entitySearch = ref('')
const connectionSearch = ref('')

/** Local UI state, not derived reactively from `modelValue`: "exclude, nothing excluded
 * yet" is data-identical to "unrestricted", so re-deriving the mode from data on every
 * render would snap the picker back to unrestricted the instant the user picks "exclude"
 * before they've added a single exclusion. Seeded once from the incoming data (this
 * component remounts fresh whenever the parent switches tabs or definitions, so a stale
 * initial guess is never an issue). */
const entityMode = ref<ScopeMode>(entityScopeMode(props.modelValue))
const connectionMode = ref<ScopeMode>(connectionScopeMode(props.modelValue))

const setEntityMode = (mode: ScopeMode) => {
  entityMode.value = mode
  emit('update:modelValue', withEntityScopeMode(props.modelValue, mode))
}
const setConnectionMode = (mode: ScopeMode) => {
  connectionMode.value = mode
  emit('update:modelValue', withConnectionScopeMode(props.modelValue, mode))
}

const domainGroups = computed(() => groupByDomain(props.catalog.entity_types, props.catalog.entity_type_domains))
const visibleDomainGroups = computed(() => domainGroups.value
  .map((g) => ({ domain: g.domain, types: filterByQuery(g.types, entitySearch.value) }))
  .filter((g) => g.types.length > 0))
const visibleConnectionTypes = computed(() => filterByQuery(props.catalog.connection_types, connectionSearch.value))

const includedEntityCount = computed(() => props.modelValue.entityTypes?.length ?? 0)
const excludedEntityCount = computed(() => {
  const excludedByDomain = domainGroups.value
    .filter((g) => props.modelValue.excludedDomains.includes(g.domain))
    .reduce((n, g) => n + g.types.length, 0)
  const coveredByDomain = new Set(
    domainGroups.value.filter((g) => props.modelValue.excludedDomains.includes(g.domain)).flatMap((g) => g.types),
  )
  const explicitOutsideExcludedDomains = props.modelValue.excludedEntityTypes.filter((t) => !coveredByDomain.has(t)).length
  return excludedByDomain + explicitOutsideExcludedDomains
})

const toggleIncludedEntity = (type: string) => update({ entityTypes: toggleInList(props.modelValue.entityTypes ?? [], type) })
const toggleIncludedConnection = (type: string) =>
  update({ connectionTypes: toggleInList(props.modelValue.connectionTypes ?? [], type) })

const toggleExcludedEntity = (type: string, domain: string, typesInDomain: readonly string[]) => {
  const state = entityExclusionState(type, domain, props.modelValue.excludedDomains, props.modelValue.excludedEntityTypes)
  if (state === 'inherited') {
    emit('update:modelValue', carveOutFromDomainExclusion(props.modelValue, type, domain, typesInDomain))
  } else {
    update({ excludedEntityTypes: toggleInList(props.modelValue.excludedEntityTypes, type) })
  }
}
const toggleExcludedConnection = (type: string) =>
  update({ excludedConnectionTypes: toggleInList(props.modelValue.excludedConnectionTypes, type) })

const bulkIncludeDomain = (typesInDomain: readonly string[]) => emit('update:modelValue', includeDomain(props.modelValue, typesInDomain))
const bulkClearDomain = (typesInDomain: readonly string[]) =>
  emit('update:modelValue', excludeDomainFromIncludeList(props.modelValue, typesInDomain))
const bulkExcludeDomain = (domain: string, typesInDomain: readonly string[]) =>
  emit('update:modelValue', excludeDomain(props.modelValue, domain, typesInDomain))
const bulkReincludeDomain = (domain: string) => emit('update:modelValue', reincludeDomain(props.modelValue, domain))

const isDomainFullyIncluded = (typesInDomain: readonly string[]) =>
  typesInDomain.every((t) => (props.modelValue.entityTypes ?? []).includes(t))

/** Chip removal via keyboard, distinct from the toggle-on-click/Enter/Space a plain
 * button already gets for free — Delete/Backspace on a selected chip always removes,
 * never re-adds. */
const onChipRemoveKey = (e: KeyboardEvent, isSelected: boolean, remove: () => void) => {
  if (isSelected && (e.key === 'Delete' || e.key === 'Backspace')) { e.preventDefault(); remove() }
}
</script>

<template>
  <div>
    <fieldset>
      <legend>Entity types</legend>
      <div
        class="mode-row"
        role="radiogroup"
        aria-label="Entity type scope mode"
      >
        <label><input
          type="radio"
          name="entity-scope-mode"
          :checked="entityMode === 'unrestricted'"
          @change="setEntityMode('unrestricted')"
        > Include all entity types</label>
        <label><input
          type="radio"
          name="entity-scope-mode"
          :checked="entityMode === 'include'"
          @change="setEntityMode('include')"
        > Include only selected entity types</label>
        <label><input
          type="radio"
          name="entity-scope-mode"
          :checked="entityMode === 'exclude'"
          @change="setEntityMode('exclude')"
        > Exclude selected entity types</label>
      </div>

      <template v-if="entityMode !== 'unrestricted'">
        <p class="counts">
          {{ entityMode === 'include' ? `${includedEntityCount} type(s) included` : `${excludedEntityCount} type(s) excluded` }}
        </p>
        <input
          v-model="entitySearch"
          type="search"
          class="type-ahead"
          placeholder="Search entity types…"
          aria-label="Search entity types"
        >
        <p
          v-if="visibleDomainGroups.length === 0"
          class="empty-hint"
        >
          No types match "{{ entitySearch }}" — try a different domain or term.
        </p>
        <div
          v-for="group in visibleDomainGroups"
          :key="group.domain"
          class="domain-group"
        >
          <div class="domain-head">
            <span class="domain-name">{{ group.domain }}</span>
            <button
              v-if="entityMode === 'include'"
              type="button"
              class="bulk-btn"
              @click="isDomainFullyIncluded(group.types) ? bulkClearDomain(group.types) : bulkIncludeDomain(group.types)"
            >
              {{ isDomainFullyIncluded(group.types) ? 'Clear this domain' : 'Include all of this domain' }}
            </button>
            <button
              v-else
              type="button"
              class="bulk-btn"
              @click="modelValue.excludedDomains.includes(group.domain)
                ? bulkReincludeDomain(group.domain)
                : bulkExcludeDomain(group.domain, group.types)"
            >
              {{ modelValue.excludedDomains.includes(group.domain) ? 'Stop excluding this domain' : 'Exclude all of this domain' }}
            </button>
          </div>
          <div class="chip-row">
            <template v-if="entityMode === 'include'">
              <button
                v-for="t in group.types"
                :key="t"
                type="button"
                class="chip"
                :class="{ on: (modelValue.entityTypes ?? []).includes(t) }"
                :aria-pressed="(modelValue.entityTypes ?? []).includes(t)"
                @click="toggleIncludedEntity(t)"
                @keydown="onChipRemoveKey($event, (modelValue.entityTypes ?? []).includes(t), () => toggleIncludedEntity(t))"
              >
                {{ t }}
              </button>
            </template>
            <template v-else>
              <button
                v-for="t in group.types"
                :key="t"
                type="button"
                class="chip"
                :class="entityExclusionState(t, group.domain, modelValue.excludedDomains, modelValue.excludedEntityTypes)"
                :aria-pressed="entityExclusionState(t, group.domain, modelValue.excludedDomains, modelValue.excludedEntityTypes) !== 'none'"
                :title="entityExclusionState(t, group.domain, modelValue.excludedDomains, modelValue.excludedEntityTypes) === 'inherited'
                  ? 'Excluded via this domain — activate to keep this type included instead'
                  : undefined"
                @click="toggleExcludedEntity(t, group.domain, group.types)"
                @keydown="onChipRemoveKey(
                  $event,
                  entityExclusionState(t, group.domain, modelValue.excludedDomains, modelValue.excludedEntityTypes) === 'explicit',
                  () => toggleExcludedEntity(t, group.domain, group.types),
                )"
              >
                {{ t }}
              </button>
            </template>
          </div>
        </div>
      </template>
    </fieldset>

    <fieldset>
      <legend>Connection types</legend>
      <div
        class="mode-row"
        role="radiogroup"
        aria-label="Connection type scope mode"
      >
        <label><input
          type="radio"
          name="connection-scope-mode"
          :checked="connectionMode === 'unrestricted'"
          @change="setConnectionMode('unrestricted')"
        > Include all connection types</label>
        <label><input
          type="radio"
          name="connection-scope-mode"
          :checked="connectionMode === 'include'"
          @change="setConnectionMode('include')"
        > Include only selected connection types</label>
        <label><input
          type="radio"
          name="connection-scope-mode"
          :checked="connectionMode === 'exclude'"
          @change="setConnectionMode('exclude')"
        > Exclude selected connection types</label>
      </div>

      <template v-if="connectionMode !== 'unrestricted'">
        <p class="counts">
          {{ connectionMode === 'include'
            ? `${modelValue.connectionTypes?.length ?? 0} type(s) included`
            : `${modelValue.excludedConnectionTypes.length} type(s) excluded` }}
        </p>
        <input
          v-model="connectionSearch"
          type="search"
          class="type-ahead"
          placeholder="Search connection types…"
          aria-label="Search connection types"
        >
        <p
          v-if="visibleConnectionTypes.length === 0"
          class="empty-hint"
        >
          No types match "{{ connectionSearch }}" — try a different term.
        </p>
        <div class="chip-row">
          <template v-if="connectionMode === 'include'">
            <button
              v-for="t in visibleConnectionTypes"
              :key="t"
              type="button"
              class="chip"
              :class="{ on: (modelValue.connectionTypes ?? []).includes(t) }"
              :aria-pressed="(modelValue.connectionTypes ?? []).includes(t)"
              @click="toggleIncludedConnection(t)"
              @keydown="onChipRemoveKey($event, (modelValue.connectionTypes ?? []).includes(t), () => toggleIncludedConnection(t))"
            >
              {{ t }}
            </button>
          </template>
          <template v-else>
            <button
              v-for="t in visibleConnectionTypes"
              :key="t"
              type="button"
              class="chip"
              :class="{ explicit: modelValue.excludedConnectionTypes.includes(t) }"
              :aria-pressed="modelValue.excludedConnectionTypes.includes(t)"
              @click="toggleExcludedConnection(t)"
              @keydown="onChipRemoveKey($event, modelValue.excludedConnectionTypes.includes(t), () => toggleExcludedConnection(t))"
            >
              {{ t }}
            </button>
          </template>
        </div>
      </template>
    </fieldset>
  </div>
</template>

<style scoped>
fieldset { border: 1px solid #d1d5db; border-radius: 8px; margin: 10px 0; padding: 8px 12px; }
.mode-row { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: #374151; margin: 4px 0 8px; }
.counts { font-size: 12px; color: #6b7280; margin: 4px 0; }
.type-ahead {
  display: block; width: 100%; padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 13px; font-family: inherit; box-sizing: border-box; margin: 4px 0 8px;
}
.empty-hint { font-size: 12px; color: #92400e; background: #fef3c7; padding: 6px 10px; border-radius: 6px; }
.domain-group { margin: 8px 0; }
.domain-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.domain-name { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
.bulk-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 99px; padding: 2px 9px; font-size: 11px; font-weight: 600; cursor: pointer;
}
.bulk-btn:hover { border-color: #6366f1; color: #4338ca; }
.bulk-btn:focus-visible { outline: 2px solid #6366f1; outline-offset: 2px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  appearance: none; border: 1px solid #d1d5db; background: #fff; border-radius: 999px;
  padding: 4px 10px; font-size: 12px; color: #374151; cursor: pointer;
}
.chip:hover { border-color: #6366f1; color: #4338ca; }
.chip:focus-visible { outline: 2px solid #6366f1; outline-offset: 2px; }
.chip.on { background: #6366f1; border-color: #6366f1; color: #fff; }
.chip.explicit { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }
.chip.inherited { background: #fef3c7; border-color: #fcd34d; color: #92400e; }
</style>
