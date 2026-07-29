<script setup lang="ts">
/** One catalog row: identity (representation glyph, name, slug, needs-input marker,
 * description), version, tier + fork lineage badges, collapsible scope summary, and the
 * per-tier action set. Pure display + emits; catalog state (search/sort/pins) stays in
 * the list. */
import type { ViewpointDefinitionEnvelope } from '../../domain'
import { tierDisplayLowercase } from './TierBadge.helpers'
import { formatScopeSummary } from '../views/ViewpointsManagementView.helpers'
import {
  REPRESENTATION_BADGES, brokenReferenceCount, brokenReferenceSummary,
  collapsedScopeSummary, definitionNeedsInput, representationOf,
} from './ViewpointDefinitionsList.helpers'

defineProps<{
  def: ViewpointDefinitionEnvelope
  pinned: boolean
  scopeExpanded: boolean
  writeBlocked: boolean
}>()
const emit = defineEmits<{
  execute: []
  edit: []
  delete: []
  togglePin: []
  toggleScope: []
}>()
</script>

<template>
  <tr>
    <td class="def-main">
      <span class="def-name">
        <span
          class="rep-badge"
          :title="REPRESENTATION_BADGES[representationOf(def)].label"
        >{{ REPRESENTATION_BADGES[representationOf(def)].glyph }}</span>
        {{ def.name }}
        <span class="def-slug">({{ def.slug }})</span>
        <span
          v-if="definitionNeedsInput(def)"
          class="needs-input"
          title="Prompts for input before running (required parameters)"
        >needs input</span>
        <span
          v-if="brokenReferenceCount(def) > 0"
          class="broken-refs"
          :title="brokenReferenceSummary(def)"
        >⚠ {{ brokenReferenceCount(def) }} broken
          {{ brokenReferenceCount(def) === 1 ? 'reference' : 'references' }}</span>
      </span>
      <span
        v-if="def.description"
        class="def-desc"
      >{{ def.description }}</span>
    </td>
    <td>{{ def.version }}</td>
    <td>
      <span
        class="tier-tag"
        :class="`tier-${def.tier}`"
      >{{ tierDisplayLowercase(def.tier) }}</span>
      <span
        v-if="def.forked_from"
        class="fork-tag"
        :class="`fork-${def.fork_status ?? 'current'}`"
        :title="def.fork_status === 'stale'
          ? `Origin '${def.forked_from.slug}' has changed since this fork was created`
          : def.fork_status === 'origin-missing'
            ? `Origin '${def.forked_from.slug}' no longer exists`
            : `Forked from '${def.forked_from.slug}' v${def.forked_from.version}`"
      >
        ⑂ {{ def.forked_from.slug }}{{ def.fork_status === 'stale' ? ' (origin changed)'
          : def.fork_status === 'origin-missing' ? ' (origin missing)' : '' }}
      </span>
    </td>
    <td class="scope-cell">
      <button
        type="button"
        class="scope-toggle"
        :aria-expanded="scopeExpanded"
        @click="emit('toggleScope')"
      >
        {{ collapsedScopeSummary(def.scope_summary) }} {{ scopeExpanded ? '▾' : '▸' }}
      </button>
      <span
        v-if="scopeExpanded"
        class="scope-full"
      >{{ formatScopeSummary(def.scope_summary) }}</span>
    </td>
    <td class="actions-cell">
      <div class="row-actions">
        <button
          type="button"
          class="pin-btn"
          :class="{ 'pin-btn--active': pinned }"
          :aria-label="pinned ? `Unpin ${def.slug}` : `Pin ${def.slug}`"
          :aria-pressed="pinned"
          @click="emit('togglePin')"
        >
          {{ pinned ? '★' : '☆' }}
        </button>
        <button
          type="button"
          class="btn"
          @click="emit('execute')"
        >
          Execute
        </button>
        <button
          v-if="def.tier === 'engagement'"
          type="button"
          class="btn"
          :disabled="writeBlocked"
          @click="emit('edit')"
        >
          Edit
        </button>
        <button
          v-if="def.tier === 'engagement'"
          type="button"
          class="btn btn--danger"
          :disabled="writeBlocked"
          @click="emit('delete')"
        >
          Delete
        </button>
        <button
          v-else
          type="button"
          class="btn"
          title="Opens this read-only master so you can adjust it and keep your version with Save as…"
          @click="emit('edit')"
        >
          Customize…
        </button>
      </div>
    </td>
  </tr>
</template>

<style scoped>
td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #e5e7eb; font-size: 13px; vertical-align: top; }
.def-main { max-width: 380px; }
.def-name { display: block; font-weight: 600; color: #111827; }
.def-slug { font-weight: 400; color: #9ca3af; font-size: 12px; }
.rep-badge { color: #6366f1; margin-right: 2px; }
.needs-input { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; background: #fef3c7; color: #92400e; border-radius: 99px; padding: 1px 7px; margin-left: 6px; vertical-align: middle; }
.broken-refs {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  background: #fee2e2; color: #991b1b; border-radius: 99px; padding: 1px 7px;
  margin-left: 6px; vertical-align: middle; white-space: nowrap;
}
.def-desc { display: block; font-size: 12px; color: #6b7280; margin-top: 2px; }
.tier-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 99px; }
.tier-engagement { background: #dcfce7; color: #166534; }
.tier-enterprise { background: #dbeafe; color: #1e40af; }
.tier-module { background: #f3f4f6; color: #6b7280; }
.fork-tag { font-size: 11px; padding: 2px 8px; border-radius: 99px; margin-left: 4px; white-space: nowrap; }
.fork-current { background: #f3f4f6; color: #6b7280; }
.fork-stale { background: #fef3c7; color: #92400e; }
.fork-origin-missing { background: #fee2e2; color: #991b1b; }
/* #9ca3af, not #d1d5db: the unpinned star is a control, and at the paler grey it sat at a
   1.35 contrast ratio against the row — legible only if you already knew it was there. */
.pin-btn { border: none; background: none; cursor: pointer; font-size: 15px; color: #9ca3af; padding: 0 4px; }
.pin-btn:hover { color: #6b7280; }
.pin-btn--active { color: #d97706; }
.scope-cell { max-width: 260px; }
.scope-toggle { appearance: none; border: none; background: none; color: #374151; font-size: 12.5px; cursor: pointer; padding: 0; text-align: left; }
.scope-toggle:hover { color: #4338ca; }
.scope-full { display: block; font-size: 11.5px; color: #6b7280; margin-top: 3px; }
.actions-cell { white-space: nowrap; }
.row-actions { display: flex; align-items: center; gap: 6px; }
.btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn:hover:not(:disabled) { border-color: #6366f1; color: #4338ca; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--danger:hover:not(:disabled) { border-color: #dc2626; color: #b91c1c; background: #fef2f2; }
</style>
