<script setup lang="ts">
/**
 * Who authored this node, and which other analyses draw on it.
 *
 * Two facts, shown apart. An FMEA that enumerates failure modes against an STPA's control structure
 * shows those components in its own working set; if they render as though the FMEA authored them,
 * the provenance that makes the combined analysis trustworthy is gone — and so is the reason not to
 * have copied them in the first place. So a borrowed node says whose it is, and a native one says
 * nothing about borrowers it does not have.
 *
 * Both lists arrive already filtered to what the reader may see (see `assurance_provenance` on the
 * backend): an analysis above the ceiling is absent rather than named, so this component never has
 * to reason about clearance. What to show and where a link goes are in the helpers, tested there.
 */
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  AUTHOR_LABEL,
  BORROWERS_LABEL,
  analysisRoute,
  hasProvenance,
  type AssuranceAnalysisSummary,
} from './AssuranceProvenance.helpers'

const props = defineProps<{
  authoredBy: AssuranceAnalysisSummary | null
  participatesIn: AssuranceAnalysisSummary[]
}>()

const show = computed(() =>
  hasProvenance({ authored_by: props.authoredBy, participates_in: props.participatesIn }),
)
</script>

<template>
  <div
    v-if="show"
    class="provenance"
  >
    <div class="section-label">
      Provenance
    </div>

    <div
      v-if="props.authoredBy"
      class="provenance-row"
    >
      <span class="provenance-label">{{ AUTHOR_LABEL }}</span>
      <RouterLink
        class="provenance-analysis"
        :to="analysisRoute(props.authoredBy.analysis_id)"
      >
        <span class="provenance-method">{{ props.authoredBy.method }}</span>
        <span class="provenance-name">{{ props.authoredBy.name }}</span>
      </RouterLink>
    </div>

    <div
      v-if="props.participatesIn.length > 0"
      class="provenance-row"
    >
      <span class="provenance-label">{{ BORROWERS_LABEL }}</span>
      <span class="provenance-borrowers">
        <RouterLink
          v-for="analysis in props.participatesIn"
          :key="analysis.analysis_id"
          class="provenance-analysis"
          :to="analysisRoute(analysis.analysis_id)"
        >
          <span class="provenance-method">{{ analysis.method }}</span>
          <span class="provenance-name">{{ analysis.name }}</span>
        </RouterLink>
      </span>
    </div>
  </div>
</template>

<style scoped>
.provenance { padding: 12px 16px; border-top: 1px solid #eef2f7; }
.section-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .04em; color: #94a3b8; margin-bottom: 8px;
}
.provenance-row { display: flex; gap: 10px; align-items: baseline; margin-bottom: 6px; font-size: 12px; }
.provenance-label { color: #64748b; min-width: 84px; flex-shrink: 0; }
.provenance-borrowers { display: flex; flex-direction: column; gap: 4px; }
.provenance-analysis { display: inline-flex; gap: 6px; align-items: baseline; text-decoration: none; }
.provenance-analysis:hover .provenance-name { text-decoration: underline; }
.provenance-method {
  font-size: 10px; font-weight: 700; color: #1d4ed8;
  background: #eff6ff; border-radius: 3px; padding: 1px 5px;
}
.provenance-name { color: #111827; }
</style>
