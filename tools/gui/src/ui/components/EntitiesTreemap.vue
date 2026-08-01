<script setup lang="ts">
/**
 * The entity catalog as a treemap: grouped by domain (or by subdomain once a domain is chosen),
 * sized by total connections.
 *
 * An adapter now, not a treemap. The layout, pan/zoom, tooltip placement and legibility thresholds
 * moved to `Treemap`, which the assurance browse surface draws through as well; what stays here is
 * the ArchiMate vocabulary — which domain a group is, what colour it takes, which glyph an entity
 * type deserves, and where clicking one goes. That split is the whole point: the shared component
 * names none of it, so a second module can use it without inheriting the first one's words.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { EntitySummary } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import Treemap from './Treemap.vue'
import { groupLeaves, type TreemapLeaf } from './Treemap.helpers'
import { friendlyEntityId, getDomainColor, getDomainLabel, getEntityConnectionTotal } from '../lib/domains'
import { entityDetailRoute } from '../router/artifactRoutes'

const props = defineProps<{ items: EntitySummary[]; activeDomain: string }>()

const router = useRouter()

const groupMode = computed(() => (props.activeDomain ? 'subdomain' : 'domain'))
const domainColor = computed(() => getDomainColor(props.activeDomain))

const byId = computed(() => new Map(props.items.map((entity) => [entity.artifact_id, entity])))

const leafOf = (entity: EntitySummary): TreemapLeaf => {
  const connections = getEntityConnectionTotal(entity)
  return {
    key: entity.artifact_id,
    label: entity.name || entity.artifact_id,
    meta: `${connections} connections`,
    value: connections,
    color: groupMode.value === 'domain' ? getDomainColor(entity.domain) : domainColor.value,
  }
}

const groupOf = (entity: EntitySummary) => ({
  name: groupMode.value === 'domain' ? getDomainLabel(entity.domain) : entity.subdomain || 'General',
  color: groupMode.value === 'domain' ? getDomainColor(entity.domain) : domainColor.value,
})

const groups = computed(() => groupLeaves(props.items, leafOf, groupOf))

const note = computed(() =>
  'Sized by total connections. Drag to pan, wheel to zoom. '
  + (groupMode.value === 'domain' ? 'Grouped by domain.' : 'Grouped by subdomain.'))

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
