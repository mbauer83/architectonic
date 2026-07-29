<script setup lang="ts">
/**
 * Read-only derived security attributes for one entity (C-S4): values from the
 * ACTIVE signal snapshot via the same metrics use case the MCP tool serializes.
 * ABSENT unless signals are available and an active snapshot anchors this entity —
 * locked store, unconfigured deployment, or anchor-less entity all collapse to
 * nothing. Deliberately contains no form element: the payload is disjoint from
 * every editable property (I-C10) and never enters edit-form state.
 */
import { ref, watch } from 'vue'
import { displayRows, panelVisible } from './DerivedSecurityAttributesPanel.helpers'
import type { SecurityMetricsPayload } from './SecurityPostureDashboard.helpers'

const props = defineProps<{ artifactId: string }>()

const metrics = ref<SecurityMetricsPayload | null>(null)

async function load() {
  metrics.value = null
  if (!props.artifactId) return
  try {
    const resp = await fetch(
      `/api/assurance/security-metrics?anchor_entity_id=${encodeURIComponent(props.artifactId)}`)
    if (!resp.ok) return // locked / unavailable ⇒ the panel simply is not there
    metrics.value = await resp.json() as SecurityMetricsPayload
  } catch {
    metrics.value = null
  }
}

watch(() => props.artifactId, load, { immediate: true })
</script>

<template>
  <section
    v-if="metrics && panelVisible(metrics)"
    class="derived-security"
  >
    <div class="panel-title">
      <span
        class="classification-icon"
        :title="`computed classification of the contributing records`"
      >{{ metrics.computed_classification ?? 'unclassified' }}</span>
      Derived security attributes
      <span class="readonly-tag">read-only</span>
    </div>
    <dl class="rows">
      <div
        v-for="row in displayRows(metrics)"
        :key="row.label"
        class="row"
      >
        <dt>{{ row.label }}</dt>
        <dd>{{ row.value }}</dd>
      </div>
    </dl>
    <p
      v-if="metrics.content_state === 'visibility_limited'"
      class="caveat"
    >
      Figures cover records visible at your classification ceiling only.
    </p>
    <!-- The drill-down lives here rather than on a global menu: the panel is
         rendered only when this entity HAS an active snapshot, so the link can
         never lead to an empty view. -->
    <RouterLink
      class="drill-down"
      :to="`/assurance/security/findings?anchor=${encodeURIComponent(props.artifactId)}`"
      data-testid="component-vulnerabilities-link"
    >
      View component vulnerabilities →
    </RouterLink>
  </section>
</template>

<style scoped>
.derived-security {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-left: 4px solid #1e293b;
  border-radius: 6px;
  padding: 10px 14px;
  margin-top: 12px;
}
.panel-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 8px;
}
.classification-icon {
  background: #1e293b; color: #f8fafc; border-radius: 4px;
  padding: 1px 7px; font-size: 10px; font-weight: 700;
}
.readonly-tag {
  margin-left: auto; font-size: 10px; color: #64748b;
  border: 1px solid #cbd5e1; border-radius: 3px; padding: 0 5px;
}
.rows { margin: 0; display: flex; flex-direction: column; gap: 3px; }
.row { display: flex; gap: 8px; font-size: 12px; }
.row dt { color: #64748b; min-width: 220px; }
.row dd { margin: 0; color: #0f172a; font-weight: 500; }
.caveat { font-size: 11px; color: #92400e; margin: 8px 0 0; }
.drill-down {
  display: inline-block; margin-top: 10px; font-size: 12px; font-weight: 500;
  color: #1d4ed8; text-decoration: none;
}
.drill-down:hover { text-decoration: underline; }
</style>
