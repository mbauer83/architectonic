<script setup lang="ts">
/**
 * What a diagram element says it corresponds to in the model, as links.
 *
 * Its own component because the sidebar is already the largest thing in this directory, and because
 * a correspondence list is one job: a kind, a name, a route. The parent decides *which* element's
 * correspondences these are — that decision needs the diagram, and this does not.
 */
import { RouterLink } from 'vue-router'

import type { ElementCorrespondence } from '../../domain/schemas/diagrams'
import { entityDetailRoute } from '../router/artifactRoutes'

defineProps<{ bindings: readonly ElementCorrespondence[] }>()
</script>

<template>
  <div
    v-if="bindings.length"
    class="det-bindings"
  >
    <h4 class="det-bindings-hdr">
      Model correspondence
    </h4>
    <ul class="det-bindings-list">
      <li
        v-for="binding in bindings"
        :key="`${binding.correspondence_kind}:${binding.artifact_id}`"
      >
        <span class="chip chip-kind">{{ binding.correspondence_kind }}</span>
        <RouterLink
          class="det-binding-link"
          :to="entityDetailRoute(binding.artifact_id)"
        >
          {{ binding.name ?? binding.artifact_id }}
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.det-bindings { margin-bottom: 8px; }
.det-bindings-hdr {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #6b7280;
  margin: 0 0 4px;
  font-weight: 600;
}
.det-bindings-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.det-bindings-list li { display: flex; align-items: baseline; gap: 6px; font-size: 12px; }
.chip { font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: 500; background: #f3f4f6; color: #374151; }
.chip-kind { background: #e0e7ff; color: #3730a3; flex: 0 0 auto; }
.det-binding-link { color: #1d4ed8; text-decoration: none; }
.det-binding-link:hover { text-decoration: underline; }
</style>
