<script setup lang="ts">
import { entityDetailRoute } from '../router/artifactRoutes'
/**
 * The graph explorer's right-hand detail panel: the selected entity or edge, whichever is
 * current, under a headline naming what is selected.
 *
 * Split out of `GraphExploreView` because that view had grown past the source-length policy
 * and this is the part of it with the fewest ties to the rest — it reads a selection and
 * renders it, and mutates nothing.
 */
import { RouterLink } from 'vue-router'
import type { GraphEdge } from '../composables/useForceGraph'
import type { ConnectionItemSummary, EntityDetail } from '../../domain'
import EdgeConnectionDetails from './EdgeConnectionDetails.vue'
import GraphNodeDetails from './GraphNodeDetails.vue'

defineProps<{
  selectedId: string | null
  selectedEdge: GraphEdge | null
  selectedEdgeSummary: ConnectionItemSummary | null
  detail: EntityDetail | null
  loading: boolean
  errorMessage: string | null
}>()
</script>

<template>
  <aside class="graph-sidebar">
    <!-- The selected entity's own name is the headline, and it is the way through to its
         detail page — the same affordance the diagram sidebar offers, rather than a static
         word above a field list that happens to contain the link. -->
    <h2 class="sidebar-title">
      <RouterLink
        v-if="detail && selectedId"
        :to="entityDetailRoute(selectedId)"
        class="sidebar-title-link"
      >
        {{ detail.name }}
      </RouterLink>
      <template v-else>
        Details
      </template>
    </h2>
    <div
      v-if="!selectedId && !selectedEdge"
      class="sidebar-empty"
    >
      Click a node or edge to view details
    </div>
    <EdgeConnectionDetails
      v-else-if="selectedEdge"
      :edge="selectedEdge"
      :summary="selectedEdgeSummary"
    />
    <div
      v-else-if="loading"
      class="sidebar-loading"
    >
      Loading...
    </div>
    <div
      v-else-if="errorMessage"
      class="sidebar-error"
    >
      {{ errorMessage }}
    </div>
    <GraphNodeDetails
      v-else-if="detail && selectedId"
      :detail="detail"
      :selected-id="selectedId"
    />
  </aside>
</template>

<style scoped>
.graph-sidebar {
  width: 320px; background: white; border-left: 1px solid #e5e7eb;
  padding: 16px; overflow-y: auto; flex-shrink: 0;
}
.sidebar-title { font-size: 14px; font-weight: 600; color: #374151; margin-bottom: 16px; }
/* Matches the diagram sidebar's `det-name`: the entity's name, sized as the heading it is,
   in the link colour so it reads as the way through to the entity rather than a caption. */
.sidebar-title-link {
  font-size: 16px; font-weight: 700; color: #1d4ed8; text-decoration: none; line-height: 1.3;
}
.sidebar-title-link:hover { text-decoration: underline; }
.sidebar-empty, .sidebar-loading { font-size: 13px; color: #6b7280; }
.sidebar-error { font-size: 13px; color: #dc2626; }
</style>
