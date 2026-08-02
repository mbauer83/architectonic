<script setup lang="ts">
/**
 * The entity catalog as a treemap: grouped by domain, or by entity type once a domain is chosen,
 * sized by total connections.
 *
 * An adapter now, not a treemap. The layout, pan/zoom, tooltip placement and legibility thresholds
 * moved to `Treemap`, which the assurance browse surface draws through as well; the ArchiMate
 * vocabulary — which domain a group is, what colour it takes, how an entity is weighed — moved to
 * `EntitiesTreemap.helpers`, mirroring `AssuranceTreemap.helpers` on the other surface. What stays
 * here is what only a component can do: which glyph an entity type deserves, and where clicking one
 * goes. The split is the whole point twice over: the shared component names none of the vocabulary,
 * so a second module can use it without inheriting the first one's words — and the vocabulary is
 * testable, which logic inside an SFC is not, because these tests run in `node` and mount nothing.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { EntitySummary } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import Treemap from './Treemap.vue'
import { entityTreemapGroups, treemapNote } from './EntitiesTreemap.helpers'
import { friendlyEntityId } from '../lib/domains'
import { entityDetailRoute } from '../router/artifactRoutes'

const props = defineProps<{ items: EntitySummary[]; activeDomain: string }>()

const router = useRouter()

const byId = computed(() => new Map(props.items.map((entity) => [entity.artifact_id, entity])))

const groups = computed(() => entityTreemapGroups(props.items, props.activeDomain))

const note = computed(() => treemapNote(props.activeDomain))

const openEntity = (id: string) => void router.push(entityDetailRoute(id))
const entityFor = (key: string): EntitySummary | undefined => byId.value.get(key)
</script>

<template>
  <Treemap
    :groups="groups"
    :note="note"
    @select="openEntity"
  >
    <template #glyph="{ leaf, x, y, size }">
      <ArchimateTypeGlyph
        :type="entityFor(leaf.key)?.artifact_type ?? ''"
        :x="x"
        :y="y"
        :size="size"
        class="leaf-glyph"
      />
    </template>

    <template #tooltip="{ leaf }">
      <div class="tooltip-head">
        <ArchimateTypeGlyph
          :type="entityFor(leaf.key)?.artifact_type ?? ''"
          :size="18"
          class="tooltip-glyph"
        />
        <div>
          <div class="tooltip-name">
            {{ entityFor(leaf.key)?.name || friendlyEntityId(leaf.key) }}
          </div>
          <div class="tooltip-type">
            {{ entityFor(leaf.key)?.artifact_type }}
          </div>
        </div>
      </div>
      <div class="tooltip-id">
        {{ leaf.key }}
      </div>
    </template>
  </Treemap>
</template>

<style scoped>
.leaf-glyph { color: #1f2937; fill: none; }
.tooltip-head { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; }
.tooltip-glyph { color: #1f2937; fill: none; flex: 0 0 auto; }
.tooltip-name { font-size: 13px; font-weight: 600; color: #111827; }
.tooltip-type { font-size: 11px; color: #6b7280; }
.tooltip-id { font-size: 11px; color: #6b7280; font-family: monospace; word-break: break-all; }
</style>
