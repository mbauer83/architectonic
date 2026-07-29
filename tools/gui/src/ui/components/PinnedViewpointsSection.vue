<script setup lang="ts">
/** Home's pinned-definitions quick-access section: pins are set from the viewpoints
 * management list and just read here — fully self-contained, so Home only has to mount
 * it. A pin whose definition has since been pruned from the effective catalog (see
 * `ViewpointPins.pruned`) is silently omitted, not rendered as a broken link. */
import { inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { RouterLink } from 'vue-router'
import { modelServiceKey } from '../keys'
import type { ViewpointDefinitionEnvelope } from '../../domain'
import { executionRouteFor } from '../views/ViewpointsManagementView.helpers'

const svc = inject(modelServiceKey)!
const pinned = ref<readonly ViewpointDefinitionEnvelope[]>([])
const loaded = ref(false)

onMounted(async () => {
  const [pins, definitions] = await Promise.all([
    Effect.runPromise(svc.getViewpointPins()).catch(() => ({ slugs: [] as readonly string[] })),
    Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [] as readonly ViewpointDefinitionEnvelope[]),
  ])
  const bySlug = new Map(definitions.map((d) => [d.slug, d]))
  pinned.value = pins.slugs.map((slug) => bySlug.get(slug)).filter((d): d is ViewpointDefinitionEnvelope => d !== undefined)
  loaded.value = true
})
</script>

<template>
  <template v-if="loaded && pinned.length > 0">
    <h2 class="section-title">
      Pinned Viewpoints
    </h2>
    <div class="pinned-grid">
      <RouterLink
        v-for="def in pinned"
        :key="def.slug"
        :to="executionRouteFor(def)"
        class="pinned-card"
      >
        <span class="pinned-name">{{ def.name }}</span>
        <span class="pinned-slug">{{ def.slug }}</span>
      </RouterLink>
    </div>
  </template>
</template>

<style scoped>
.section-title { font-size: 16px; font-weight: 600; margin: 28px 0 12px; color: #374151; }
.pinned-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.pinned-card {
  background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 12px 16px;
  display: flex; flex-direction: column; gap: 2px; color: inherit;
}
.pinned-card:hover { text-decoration: none; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.pinned-name { font-weight: 500; font-size: 13px; }
.pinned-slug { font-size: 11px; color: #6b7280; font-family: monospace; }
</style>
