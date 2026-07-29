<script setup lang="ts">
/**
 * The assurance node list as a treemap — the same view the architecture catalog offers, through the
 * same component.
 *
 * An adapter, like `EntitiesTreemap`: the shared `Treemap` owns layout, pan/zoom and legibility, and
 * this supplies the assurance vocabulary — grouped by node type, coloured by type, sized by the
 * connections in the reader's visible set. Clicking a tile opens the node's own page, which is where
 * the browse table sends a click too.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Treemap from './Treemap.vue'
import {
  TREEMAP_NOTE,
  assuranceTreemapGroups,
  nodeTypeColor,
  type AssuranceTreemapNode,
} from './AssuranceTreemap.helpers'

const props = defineProps<{ items: readonly AssuranceTreemapNode[] }>()

const router = useRouter()

const groups = computed(() => assuranceTreemapGroups(props.items))
const byId = computed(() => new Map(props.items.map((node) => [node.node_id, node])))
const nodeFor = (key: string) => byId.value.get(key)

const openNode = (nodeId: string) =>
  void router.push({ path: `/assurance/node/${encodeURIComponent(nodeId)}` })
</script>

<template>
  <Treemap
    :groups="groups"
    :note="TREEMAP_NOTE"
    @select="openNode"
  >
    <!-- A coloured dot rather than a glyph: assurance node types have no icon set of their own, and
         borrowing the ArchiMate glyphs would label a hazard with an architecture symbol. -->
    <template #glyph="{ leaf, x, y, size }">
      <circle
        class="leaf-dot"
        :cx="x + size / 2"
        :cy="y + size / 2"
        :r="Math.max(2, size / 3)"
        :fill="nodeTypeColor(nodeFor(leaf.key)?.node_type ?? '')"
      />
    </template>

    <template #tooltip="{ leaf }">
      <div class="tooltip-name">
        {{ nodeFor(leaf.key)?.name || leaf.key }}
      </div>
      <div class="tooltip-type">
        {{ nodeFor(leaf.key)?.node_type }} · {{ leaf.meta }}
      </div>
      <div class="tooltip-id">
        {{ leaf.key }}
      </div>
    </template>
  </Treemap>
</template>

<style scoped>
.leaf-dot { stroke: rgba(255, 255, 255, .85); stroke-width: 1; }
.tooltip-name { font-size: 13px; font-weight: 600; color: #111827; margin-bottom: 2px; }
.tooltip-type { font-size: 11px; color: #6b7280; margin-bottom: 6px; }
.tooltip-id { font-size: 11px; color: #6b7280; font-family: monospace; word-break: break-all; }
</style>
