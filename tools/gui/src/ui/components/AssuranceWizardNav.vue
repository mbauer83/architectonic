<script setup lang="ts">
/**
 * Left-hand navigation for the assurance surfaces: the analyses you can start, and the places
 * the results live.
 *
 * The wizards used to be reachable only from the assurance hub, so getting from a node list to
 * "record a CAST" meant navigating away and back. Putting them beside the list mirrors the
 * architecture side, where the group tree sits next to the entity table rather than on a
 * separate page.
 *
 * A flat, declared list rather than a component per link: every entry is the same thing — a
 * route with a label — and hand-written blocks would drift.
 *
 * Below the links sits the filing tree: which group each analysis is in, and what each analysis
 * wrote. That is what makes this a navigation surface rather than a menu — "what analyses exist and
 * what is in them" was previously answerable only through a picker above the node list.
 */
import { RouterLink } from 'vue-router'
import AssuranceFilingTree from './AssuranceFilingTree.vue'
import { assuranceAnalysisCreateRoute, assuranceSecurityFindingsListRoute } from '../router/artifactRoutes'

const props = defineProps<{
  /** The analysis the surface beside this nav is scoped to, so the tree agrees with it. */
  selectedAnalysisId?: string | null
}>()

interface NavEntry {
  to: string
  label: string
}

interface NavSection {
  title: string
  entries: readonly NavEntry[]
}

//: Ordered by how an analysis actually proceeds: hazard analysis first, then the argument
//: built on it, then the registers that track what it found.
const SECTIONS: readonly NavSection[] = [
  {
    title: 'Record an analysis',
    entries: [
      { to: assuranceAnalysisCreateRoute('stpa'), label: 'STPA — hazard analysis' },
      { to: assuranceAnalysisCreateRoute('cast'), label: 'CAST — incident analysis' },
      { to: assuranceAnalysisCreateRoute('fmea'), label: 'FMEA — failure modes' },
      { to: assuranceAnalysisCreateRoute('gsn'), label: 'Assurance case / GSN' },
      { to: '/assurance/supply-chain', label: 'Supply chain' },
      { to: assuranceAnalysisCreateRoute('grc'), label: 'Governance, risk & compliance' },
    ],
  },
  //: No standalone "FMEA matrix" entry: there is one matrix per FMEA analysis, and a single link
  //: could only show one of them — or, as it did, all of them in one table. Derived diagrams lists
  //: them per analysis, which is where a reader picks the one they mean.
  {
    title: 'Results',
    entries: [
      { to: '/assurance', label: 'All nodes' },
      { to: '/assurance/diagrams', label: 'Derived diagrams' },
      { to: assuranceSecurityFindingsListRoute(), label: 'Security findings' },
      { to: '/assurance/baselines', label: 'Baselines' },
    ],
  },
]
</script>

<template>
  <nav class="wizard-nav">
    <section
      v-for="section in SECTIONS"
      :key="section.title"
      class="nav-section"
    >
      <h2 class="nav-title">
        {{ section.title }}
      </h2>
      <RouterLink
        v-for="entry in section.entries"
        :key="entry.to"
        :to="entry.to"
        class="nav-link"
        active-class="nav-link--active"
      >
        {{ entry.label }}
      </RouterLink>
    </section>

    <section class="nav-section">
      <h2 class="nav-title">
        Filing
      </h2>
      <AssuranceFilingTree :selected-key="props.selectedAnalysisId ?? null" />
    </section>
  </nav>
</template>

<style scoped>
.wizard-nav {
  width: 232px; flex-shrink: 0; border-right: 1px solid #e5e7eb; background: #fafafa;
  padding: 12px 0; overflow-y: auto;
}
.nav-section { margin-bottom: 18px; }
.nav-title {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  color: #6b7280; margin: 0 0 6px 14px;
}
.nav-link {
  display: block; padding: 5px 14px; font-size: 12.5px; color: #374151; text-decoration: none;
  border-left: 2px solid transparent;
}
.nav-link:hover { background: #f3f4f6; color: #111827; }
/* Selected state carries its own text colour rather than relying on the hover rule, which a
   single-class active rule would otherwise lose to on hover. */
.nav-link--active {
  background: #eff6ff; color: #1d4ed8; font-weight: 600; border-left-color: #2563eb;
}
.nav-link--active:hover { background: #dbeafe; color: #1d4ed8; }
</style>
