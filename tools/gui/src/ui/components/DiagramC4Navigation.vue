<script setup lang="ts">
/** C4 breadcrumb (parent diagrams, sticky) and drill-down links (child diagrams) for a
 * model-backed C4 diagram. Pure display over `c4Navigation` — navigation itself is plain
 * RouterLinks, no state of its own. */
import type { C4Navigation } from '../../domain'

defineProps<{ c4Navigation: C4Navigation }>()
</script>

<template>
  <div>
    <!-- C4 up-banner: sticky breadcrumb showing parent C4 diagrams -->
    <div
      v-if="c4Navigation.parent_diagrams.length"
      class="c4-up-banner"
    >
      <span class="c4-level-badge">L{{ c4Navigation.current_level }}</span>
      <span
        v-if="c4Navigation.scope_entity_name"
        class="c4-scope-name"
      >{{ c4Navigation.scope_entity_name }}</span>
      <span class="c4-sep">·</span>
      <RouterLink
        v-for="p in c4Navigation.parent_diagrams"
        :key="p.diagram_id"
        :to="{ path: '/diagram', query: { id: p.diagram_id } }"
        class="c4-up-link"
      >
        ↑ {{ p.diagram_name }}
      </RouterLink>
    </div>

    <!-- C4 child links (de-emphasised; primary drill-down is via on-node badges) -->
    <div
      v-if="c4Navigation.child_diagrams.length"
      class="c4-child-nav"
    >
      <span class="c4-nav-dir">Drill down:</span>
      <RouterLink
        v-for="child in c4Navigation.child_diagrams"
        :key="child.diagram_id"
        :to="{ path: '/diagram', query: { id: child.diagram_id } }"
        class="c4-nav-link"
      >
        ⤵ {{ child.diagram_name }}
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.c4-up-banner {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 7px 12px; margin-bottom: 8px;
  background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px;
  position: sticky; top: 0; z-index: 10;
}
.c4-scope-name { font-size: 12px; color: #1e40af; font-weight: 500; }
.c4-sep { font-size: 11px; color: #9ca3af; }
.c4-up-link {
  font-size: 12px; color: #1d4ed8; text-decoration: none; font-weight: 600;
  padding: 2px 8px; background: white; border: 1px solid #bfdbfe; border-radius: 4px;
}
.c4-up-link:hover { background: #dbeafe; text-decoration: none; }
.c4-child-nav {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 5px 10px; margin-bottom: 10px;
  background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px;
}
.c4-level-badge { padding: 2px 8px; border-radius: 4px; background: #0ea5e9; color: white; font-size: 11px; font-weight: 700; }
.c4-nav-dir { font-size: 11px; font-weight: 700; color: #6b7280; white-space: nowrap; }
.c4-nav-link { font-size: 12px; color: #0369a1; text-decoration: none; padding: 2px 8px; border: 1px solid #bae6fd; border-radius: 4px; background: white; }
.c4-nav-link:hover { background: #e0f2fe; text-decoration: none; }
</style>
