<script setup lang="ts">
/** The editor's notice stack: read-only-master hint, fork-in-progress hint, version-bump
 * hint, and the clickable validation-issue list. Pure display — issue focusing stays with
 * the parent, which owns the highlighted-node overlay. */
import { computed } from 'vue'
import type {
  BrokenReference, ViewpointDefinitionEnvelope, ViewpointReferencer, ViewpointValidationIssue,
} from '../../domain'
import { withArticle } from '../lib/indefiniteArticle'

const props = withDefaults(defineProps<{
  isReadOnly: boolean
  viewingTier: ViewpointDefinitionEnvelope['tier'] | null
  forkedFromSlug: string | null
  showVersionBumpHint: boolean
  quarantinedRuleCount?: number
  brokenReferences?: readonly BrokenReference[]
  referencers: readonly ViewpointReferencer[]
  issues: readonly ViewpointValidationIssue[]
}>(), { quarantinedRuleCount: 0, brokenReferences: () => [] })
const emit = defineEmits<{ focusIssue: [issue: ViewpointValidationIssue] }>()

/** "an enterprise-tier" / "a module-tier" — the tier is only absent while nothing is loaded, in
 * which case the read-only notice is not shown at all. */
const tierWithArticle = computed(() => (props.viewingTier ? withArticle(props.viewingTier) : ''))
</script>

<template>
  <p
    v-if="isReadOnly"
    class="hint hint--readonly"
  >
    This is {{ tierWithArticle }}-tier definition and cannot be changed in place — adjust it
    freely, then use "Save as…" to keep your changes as a new engagement viewpoint.
  </p>

  <p
    v-if="forkedFromSlug"
    class="hint"
  >
    Saving as a new engagement viewpoint forked from "{{ forkedFromSlug }}" — adjust the
    slug and name, then save.
  </p>

  <p
    v-if="quarantinedRuleCount > 0"
    class="hint"
  >
    {{ quarantinedRuleCount }} inherited style rule{{ quarantinedRuleCount === 1 ? '' : 's' }}
    disabled — attribute no longer resolvable on this repository. The rule{{ quarantinedRuleCount === 1 ? ' stays' : 's stay' }}
    saved but inert; re-enable from the Presentation tab after fixing the reference.
  </p>

  <p
    v-if="showVersionBumpHint"
    class="hint"
  >
    This is a semantic edit (scope/query/presentation/representation types changed) —
    bump the version, or diagrams pinned to the current version will be flagged stale.
    <span v-if="referencers.length > 0">
      Currently pinned: {{ referencers.map((r) => r.artifact_id).join(', ') }}.
    </span>
  </p>

  <div
    v-if="brokenReferences.length > 0"
    class="broken-block"
  >
    <p class="broken-lead">
      {{ brokenReferences.length }} reference{{ brokenReferences.length === 1 ? '' : 's' }} no longer
      {{ brokenReferences.length === 1 ? 'resolves' : 'resolve' }} against the current model. Results
      are degraded until repaired — remap the reference, drop the term, or disable the affected style
      rule (Presentation tab). Saving with a bumped version acknowledges the repair.
    </p>
    <ul class="broken-list">
      <li
        v-for="(broken, i) in brokenReferences"
        :key="i"
        :class="broken.severity"
      >
        <b>{{ broken.locus }}</b>: {{ broken.kind }} <code>{{ broken.reference }}</code> no longer exists
      </li>
    </ul>
  </div>

  <ul
    v-if="issues.length > 0"
    class="issue-list"
  >
    <li
      v-for="(issue, i) in issues"
      :key="i"
      :class="issue.severity"
      @click="emit('focusIssue', issue)"
    >
      <b>{{ issue.code }}</b> ({{ issue.path }}): {{ issue.message }}
    </li>
  </ul>
</template>

<style scoped>
.hint { background: #fef3c7; color: #92400e; padding: 8px 12px; border-radius: 6px; }
.hint--readonly { background: #f3f4f6; color: #374151; }
.issue-list { list-style: none; padding: 0; }
.issue-list li { padding: 6px 10px; border-radius: 6px; margin: 4px 0; cursor: pointer; font-size: 12.5px; }
.issue-list li.error { background: #fee2e2; color: #991b1b; }
.issue-list li.warning { background: #fef3c7; color: #92400e; }
.broken-block { border: 1px solid #fecaca; border-radius: 6px; padding: 8px 12px; margin: 4px 0; }
.broken-lead { margin: 0 0 6px; font-size: 12.5px; color: #991b1b; }
.broken-list { list-style: none; padding: 0; margin: 0; }
.broken-list li { padding: 5px 10px; border-radius: 6px; margin: 3px 0; font-size: 12.5px; }
.broken-list li.ontology { background: #fee2e2; color: #991b1b; }
.broken-list li.entity-id { background: #fef3c7; color: #92400e; }
.broken-list code { font-family: ui-monospace, monospace; }
</style>
