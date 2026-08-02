<script setup lang="ts">
/**
 * Standalone, deep-linkable page for one assurance node: /assurance/nodes/:nodeId.
 * Wraps the same detail component the browse split view uses. Unknown and
 * above-ceiling ids render the identical not-found page (the backend already
 * keeps them indistinguishable); a locked store renders the locked banner.
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import AssuranceNodeDetail from '../components/AssuranceNodeDetail.vue'

const route = useRoute()
const router = useRouter()
// `nodeId`, the name the route template declares. It read `id` — the pre-0.2.0 name — so every
// deep link resolved to the empty string and the page rendered an empty detail frame for a node
// that exists, with no statement that anything was wrong.
const nodeId = computed(() => String(route.params.nodeId ?? ''))

type LoadState = 'ok' | 'not-found' | 'locked' | 'error' | 'pending'
const loadState = ref<LoadState>('pending')
</script>

<template>
  <div class="node-page">
    <div class="page-header">
      <RouterLink
        :to="{ path: '/assurance', query: { node_id: nodeId } }"
        class="back-link"
      >
        ← Open in browse
      </RouterLink>
      <span class="page-title">Assurance node</span>
      <code class="page-node-id">{{ nodeId }}</code>
    </div>

    <div
      v-if="loadState === 'not-found'"
      class="page-banner page-banner--missing"
    >
      This node does not exist — or is not visible at your current
      classification ceiling. The two cases are intentionally
      indistinguishable.
      <RouterLink to="/assurance">
        Browse visible nodes
      </RouterLink>
    </div>
    <div
      v-else-if="loadState === 'locked'"
      class="page-banner page-banner--locked"
    >
      The assurance store is locked. Run <code>arch-assurance unlock</code> and reload.
    </div>

    <div
      v-show="loadState === 'ok' || loadState === 'pending' || loadState === 'error'"
      class="detail-frame"
    >
      <AssuranceNodeDetail
        :node-id="nodeId"
        @load-state="loadState = $event"
        @close="router.push('/assurance')"
      />
    </div>
  </div>
</template>

<style scoped>
.node-page { max-width: 760px; margin: 0 auto; }
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0 14px;
}
.back-link { font-size: 13px; color: #6b7280; text-decoration: none; }
.back-link:hover { color: #374151; }
.page-title { font-size: 14px; font-weight: 600; color: #374151; }
.page-node-id { font-size: 12px; color: #6b7280; background: #f3f4f6; padding: 1px 6px; border-radius: 4px; }

.page-banner { font-size: 13px; padding: 14px 16px; border-radius: 8px; }
.page-banner--missing { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
.page-banner--missing a { margin-left: 6px; }
.page-banner--locked { background: #fef9c3; color: #854d0e; border: 1px solid #facc15; }

.detail-frame {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
</style>
