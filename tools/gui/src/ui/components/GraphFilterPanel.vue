<script setup lang="ts">
/**
 * The graph's legibility control: include and exclude along whatever levels the meta-ontology
 * declares.
 *
 * Presentational, in the split `TierFacet` established — it emits a toggle and never touches the
 * router, so URL persistence stays with the owning view's composable.
 *
 * **Collapsed, it still says what it is doing.** A filter that hides relations without saying so
 * is the defect B30 fixed — a graph whose visible edge set depends on something the reader cannot
 * see — shipped back as a feature. So the summary carries the excluded count and the clear, and
 * both are reachable without opening the panel.
 *
 * Vocabulary-free by the same contract `FilterBar` states: the caller supplies levels and values
 * already derived from the loaded graph. This names no ontology, no domain and no level id, so a
 * different meta-ontology's chain renders without a change here.
 */
import { computed, ref } from 'vue'
import type { FacetOptions, FacetSelection } from '../lib/graphFacets'

const props = defineProps<{
  /** Levels over the things the graph draws, each with the values present in it. */
  entityFacets: readonly FacetOptions[]
  /** Levels over the relations between them. */
  relationFacets: readonly FacetOptions[]
  selection: FacetSelection
  excluded: number
}>()

const emit = defineEmits<{
  toggle: [level: string, value: string]
  reset: []
}>()

const open = ref(false)

/** Nothing to filter on is not a control: an empty graph would otherwise show empty selects. */
const hasAnything = computed(
  () => props.entityFacets.length > 0 || props.relationFacets.length > 0,
)

const isExcluded = (level: string, value: string): boolean =>
  (props.selection[level] ?? []).includes(value)

/** Values read better than slugs, and this is the only place that has to know that. */
const readable = (value: string): string => value.replace(/[-_]/g, ' ')

const groups = computed(() => [
  { key: 'entity', heading: 'Elements', facets: props.entityFacets },
  { key: 'relation', heading: 'Relationships', facets: props.relationFacets },
])
</script>

<template>
  <div
    v-if="hasAnything"
    class="graph-filter"
  >
    <div class="summary">
      <button
        type="button"
        class="disclosure"
        :aria-expanded="open"
        aria-controls="graph-filter-body"
        @click="open = !open"
      >
        <span
          class="chevron"
          aria-hidden="true"
        >{{ open ? '▾' : '▸' }}</span>
        Filter
        <span
          v-if="excluded > 0"
          class="count"
        >· {{ excluded }} excluded</span>
      </button>
      <!-- "Clear", not "Reset": the viewport control beside it on this same surface is a Reset,
           and it resets the framing rather than the filter. Two controls a step apart under one
           word is a worse problem than a slightly longer one. -->
      <button
        v-if="excluded > 0"
        type="button"
        class="reset"
        @click="emit('reset')"
      >
        Clear
      </button>
    </div>

    <div
      v-show="open"
      id="graph-filter-body"
      class="body"
    >
      <template
        v-for="group in groups"
        :key="group.key"
      >
        <div
          v-if="group.facets.length > 0"
          class="group"
        >
          <p class="heading">
            {{ group.heading }}
          </p>
          <div
            v-for="facet in group.facets"
            :key="facet.level.id"
            class="level"
          >
            <p class="level-label">
              {{ facet.level.label }}
            </p>
            <div
              class="values"
              role="group"
              :aria-label="facet.level.label"
            >
              <button
                v-for="value in facet.values"
                :key="value"
                type="button"
                class="value"
                :class="{ excluded: isExcluded(facet.level.id, value) }"
                :aria-pressed="!isExcluded(facet.level.id, value)"
                @click="emit('toggle', facet.level.id, value)"
              >
                {{ readable(value) }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.graph-filter {
  /* As the layout groups beside it: wrap rather than squash. */
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 12px;
}
.summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}
.disclosure {
  border: none;
  background: none;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 0;
}
.chevron { margin-right: 4px; }
.count { color: #b45309; font-weight: 600; }
.reset {
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #374151;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
}
.reset:hover { background: #f3f4f6; }
.body {
  border-top: 1px solid #e5e7eb;
  padding: 8px;
  max-height: 40vh;
  overflow-y: auto;
}
.group + .group { margin-top: 10px; }
.heading {
  margin: 0 0 4px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.level + .level { margin-top: 6px; }
.level-label {
  margin: 0 0 3px;
  color: #374151;
  font-weight: 600;
}
.values {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.value {
  border: 1px solid #d1d5db;
  border-radius: 999px;
  background: #fff;
  color: #374151;
  font-size: 11px;
  padding: 2px 10px;
  cursor: pointer;
}
.value:hover { background: #f3f4f6; }
.value.excluded {
  background: #f3f4f6;
  color: #9ca3af;
  text-decoration: line-through;
  border-style: dashed;
}
</style>
