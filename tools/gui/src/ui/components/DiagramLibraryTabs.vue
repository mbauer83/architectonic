<script setup lang="ts">
/**
 * The two halves of the diagram library: the diagrams, and the icons their elements are drawn with.
 * Icons are presentation assets for diagram elements, so a reader looking for one looks under
 * Diagrams rather than in a top-level entry of their own.
 */
import { RouterLink } from 'vue-router'
import { diagramListRoute, iconLibraryRoute } from '../router/artifactRoutes'
</script>

<template>
  <nav
    class="library-tabs"
    aria-label="Diagram library"
  >
    <RouterLink
      class="library-tabs__tab"
      :to="diagramListRoute()"
      exact-active-class="library-tabs__tab--current"
    >
      Diagrams
    </RouterLink>
    <RouterLink
      class="library-tabs__tab"
      :to="iconLibraryRoute()"
      exact-active-class="library-tabs__tab--current"
    >
      Icons
    </RouterLink>
  </nav>
</template>

<style scoped>
.library-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
.library-tabs__tab {
  padding: 6px 12px; margin-bottom: -1px; font-size: 13px; color: var(--muted);
  border-bottom: 2px solid transparent;
}
.library-tabs__tab:hover { color: var(--text); text-decoration: none; }
.library-tabs__tab--current { color: var(--text); font-weight: 500; border-bottom-color: var(--accent); }
</style>
