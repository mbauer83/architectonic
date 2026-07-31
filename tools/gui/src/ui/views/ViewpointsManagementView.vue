<script setup lang="ts">
/**
 * Viewpoint definitions management view: list the effective merged catalog (engagement
 * definitions editable, enterprise/module read-only), and create/edit through the
 * criteria-tree builder — one save path (`persist_edit`-mode validation) shared with the
 * MCP authoring tool. No raw-YAML editing surface anywhere.
 *
 * Orchestrates state shared across the edit-mode tabs (the draft itself, validation issues,
 * the highlighted-node overlay, save); each tab owns its own tab-local concerns (see
 * ViewpointGeneralTab/ViewpointScopeTab/ViewpointQueryTab/ViewpointPresentationTab).
 */
import { computed, inject, onMounted, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useWriteBlock } from '../composables/useWriteBlock'
import { readErrorMessage } from '../lib/errors'
import type {
  CriteriaCatalog, ViewpointDefinitionEnvelope, ViewpointPersistResult, ViewpointReferencer, ViewpointValidationIssue,
} from '../../domain'
import { isEmptyQuery, mkDefinitionDraft, queryFromScopeDraft } from '../../domain/viewpointDefinitionDraft'
import { takeEphemeralViewpointDraft } from '../lib/ephemeralViewpointDraft'
import type { SelectionMode, ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { definitionFromMapping, definitionToMapping } from '../../domain/viewpointDefinitionSerialization'
import { attributeTypeTablesFromCatalog } from '../../domain/viewpointBindings'
import { groupFromMapping } from '../../domain/viewpointCriteriaSerialization'
import { resolveIssuePathNodeId } from '../../domain/viewpointIssuePath'
import { HIGHLIGHTED_NODE_ID_KEY } from '../components/CriteriaTreeBuilder.helpers'
import {
  firstErrorNodeId, isDraftDirty, isSemanticEdit, suggestForkSlug,
} from './ViewpointsManagementView.helpers'
import { useForkRuleQuarantine } from '../composables/useForkRuleQuarantine'
import ViewpointDefinitionsList from '../components/ViewpointDefinitionsList.vue'
import ViewpointEditorNotices from '../components/ViewpointEditorNotices.vue'
import ViewpointEditorTabs from '../components/ViewpointEditorTabs.vue'
import ViewpointGeneralTab from '../components/ViewpointGeneralTab.vue'
import SelectionModeSwitch from '../components/SelectionModeSwitch.vue'
import ViewpointScopeTab from '../components/ViewpointScopeTab.vue'
import ViewpointQueryTab from '../components/ViewpointQueryTab.vue'
import ViewpointPresentationTab from '../components/ViewpointPresentationTab.vue'

const svc = inject(modelServiceKey)!
const writeBlocked = useWriteBlock()
const route = useRoute()
const router = useRouter()

const highlightedNodeId = ref<string | null>(null)
provide(HIGHLIGHTED_NODE_ID_KEY, highlightedNodeId)

const mode = ref<'list' | 'edit'>('list')
const definitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
const catalog = ref<CriteriaCatalog | null>(null)
const loadError = ref<string | null>(null)
const saveError = ref<string | null>(null)

const draft = ref<ViewpointDefinitionDraft | null>(null)
const originalDraft = ref<ViewpointDefinitionDraft | null>(null)
const isCreating = ref(false)
const viewingTier = ref<ViewpointDefinitionEnvelope['tier'] | null>(null)
const isReadOnly = computed(() => viewingTier.value !== null && viewingTier.value !== 'engagement')
const activeTab = ref<'general' | 'scope' | 'query' | 'presentation'>('general')

/** Switching modes never destroys the other layer. Scope→query offers the one-way
 * conversion: an empty/absent query is seeded from the scope's entity types (the same
 * mechanical translation the engine executes for scope mode), so the population is
 * unchanged at the moment of switching. */
const setSelectionMode = (mode: SelectionMode) => {
  if (!draft.value) return
  if (mode === 'query' && isEmptyQuery(draft.value.query)) {
    draft.value.query = queryFromScopeDraft(draft.value.scope)
  }
  draft.value.selectionMode = mode
  if (activeTab.value === 'scope' || activeTab.value === 'query') {
    activeTab.value = mode
  }
}
const issues = ref<readonly ViewpointValidationIssue[]>([])
const referencers = ref<readonly ViewpointReferencer[]>([])
const saving = ref(false)

const loadDefinitions = () =>
  Effect.runPromise(svc.listViewpointDefinitions()).then((list) => { definitions.value = list })
const loadCatalog = () =>
  Effect.runPromise(svc.getCriteriaCatalog()).then((c) => { catalog.value = c })

onMounted(() => {
  Promise.all([loadDefinitions(), loadCatalog()])
    .then(() => {
      // Editor state is addressable: /viewpoints/new opens a blank draft,
      // /viewpoints/<slug>/edit opens that definition.
      const slugParam = route.params.slug
      if (typeof slugParam === 'string' && mode.value === 'list') {
        const envelope = definitions.value.find((d) => d.slug === slugParam)
        if (envelope) startEdit(envelope)
        else void router.replace('/viewpoints')
      }
    })
    .catch((reason: unknown) => { loadError.value = readErrorMessage(reason) })
  if (route.path === '/viewpoints/new') {
    startCreate()
    adoptStagedEphemeralDraft()
  }
  const seed = route.query.seedEntityCriteria
  if (typeof seed === 'string') {
    startCreate()
    try {
      draft.value!.query!.entityCriteria = groupFromMapping(JSON.parse(seed) as Record<string, unknown>, 'entity')
    } catch {
      // Malformed/stale seed param — ignore and leave the fresh, empty criteria in place.
    }
    void router.replace({ path: '/viewpoints/new', query: {} })
  }
})

// "Query model → Save as…": adopt the ephemeral query + presentation staged before navigation,
// so the new-definition editor opens pre-populated with exactly what was just run.
const adoptStagedEphemeralDraft = () => {
  const staged = takeEphemeralViewpointDraft()
  if (!staged || !draft.value) return
  if (staged.query) draft.value.query = staged.query
  if (staged.presentation) draft.value.presentation = staged.presentation
}

const startCreate = () => {
  quarantinedRuleCount.value = 0
  draft.value = mkDefinitionDraft()
  originalDraft.value = null
  forkedFromSlug.value = null
  isCreating.value = true
  viewingTier.value = 'engagement'
  issues.value = []
  referencers.value = []
  saveError.value = null
  activeTab.value = 'general'
  mode.value = 'edit'
  if (route.path !== '/viewpoints/new') void router.replace('/viewpoints/new')
}

const startEdit = (envelope: ViewpointDefinitionEnvelope) => {
  quarantinedRuleCount.value = 0
  if (route.path !== `/viewpoints/${envelope.slug}/edit`) void router.replace(`/viewpoints/${envelope.slug}/edit`)
  draft.value = definitionFromMapping(envelope)
  originalDraft.value = definitionFromMapping(envelope)
  isCreating.value = false
  viewingTier.value = envelope.tier
  issues.value = []
  saveError.value = null
  activeTab.value = 'general'
  mode.value = 'edit'
  void Effect.runPromise(svc.getViewpointReferencers(envelope.slug)).then((r) => { referencers.value = r })
}

const backToList = (options: { persisted?: boolean } = {}) => {
  const dirty = !options.persisted
    && isDraftDirty(draft.value, originalDraft.value, { isCreating: isCreating.value, isReadOnly: isReadOnly.value })
  if (dirty && !window.confirm('Discard unsaved changes to this viewpoint?')) return
  if (route.path !== '/viewpoints') void router.replace('/viewpoints')
  mode.value = 'list'
  draft.value = null
  originalDraft.value = null
  viewingTier.value = null
  forkedFromSlug.value = null
  void loadDefinitions()
}

// ── Save As: fork the open definition (any tier) into a new engagement viewpoint ──

const forkedFromSlug = ref<string | null>(null)
const { quarantinedRuleCount, quarantineDriftedRules } = useForkRuleQuarantine(svc)

const startSaveAs = () => {
  if (!draft.value) return
  if (route.path !== '/viewpoints/new') void router.replace('/viewpoints/new')
  forkedFromSlug.value = originalDraft.value?.slug ?? draft.value.slug
  draft.value.slug = suggestForkSlug(forkedFromSlug.value, definitions.value.map((d) => d.slug))
  draft.value.version = 1
  isCreating.value = true
  viewingTier.value = 'engagement'
  originalDraft.value = null
  referencers.value = []
  issues.value = []
  saveError.value = null
  activeTab.value = 'general'
  if (draft.value && catalog.value) void quarantineDriftedRules(draft.value, catalog.value)
}

const isSemantic = computed(() => draft.value && originalDraft.value && isSemanticEdit(draft.value, originalDraft.value))
const versionBumped = computed(() => draft.value && originalDraft.value && draft.value.version > originalDraft.value.version)
const showVersionBumpHint = computed(() => !isCreating.value && isSemantic.value && !versionBumped.value)

const save = () => {
  if (!draft.value || !catalog.value || isReadOnly.value) return
  saving.value = true
  saveError.value = null
  const body = { definition: definitionToMapping(draft.value, attributeTypeTablesFromCatalog(catalog.value)), dry_run: false }
  // Lineage is stamped server-side from fork_of — the client never asserts provenance.
  const call = isCreating.value
    ? svc.createViewpointDefinition(forkedFromSlug.value !== null ? { ...body, fork_of: forkedFromSlug.value } : body)
    : svc.replaceViewpointDefinition(draft.value.slug, body)
  Effect.runPromise(call).then((result: ViewpointPersistResult) => {
    saving.value = false
    if (result.ok) { backToList({ persisted: true }); return }
    issues.value = result.issues
    referencers.value = result.referencers.length > 0 ? result.referencers : referencers.value
    highlightedNodeId.value = draft.value ? firstErrorNodeId(result.issues, draft.value) : null
  }).catch((reason: unknown) => {
    saving.value = false
    saveError.value = readErrorMessage(reason)
  })
}

const focusIssue = (issue: ViewpointValidationIssue) => {
  if (!draft.value) return
  highlightedNodeId.value = resolveIssuePathNodeId(issue.path, draft.value)
}
</script>

<template>
  <div class="page">
    <h1>Viewpoints</h1>

    <p
      v-if="loadError"
      class="error"
    >
      {{ loadError }}
    </p>

    <ViewpointDefinitionsList
      v-if="mode === 'list'"
      :definitions="definitions"
      @create="startCreate"
      @edit="startEdit"
      @refresh="loadDefinitions"
      @error="loadError = $event"
    />

    <template v-else-if="draft && catalog">
      <div class="editor-topbar">
        <button
          type="button"
          class="back-btn"
          @click="backToList()"
        >
          ← Back
        </button>
        <a
          class="help-link"
          href="https://github.com/mbauer83/architectonic/blob/main/docs/03-modeling/viewpoints.md"
          target="_blank"
          rel="noopener"
          title="Viewpoints guide: scope vs query, style rules, Save as…, Test run"
        >? Help</a>
      </div>

      <ViewpointEditorNotices
        :is-read-only="isReadOnly"
        :viewing-tier="viewingTier"
        :forked-from-slug="forkedFromSlug"
        :show-version-bump-hint="Boolean(showVersionBumpHint)"
        :quarantined-rule-count="quarantinedRuleCount"
        :broken-references="definitions.find((d) => d.slug === draft?.slug)?.broken_references ?? []"
        :referencers="referencers"
        :issues="issues"
        @focus-issue="focusIssue"
      />

      <ViewpointEditorTabs
        :active-tab="activeTab"
        :selection-mode="draft.selectionMode"
        @update:active-tab="activeTab = $event"
      />
      <SelectionModeSwitch
        :model-value="draft.selectionMode"
        @update:model-value="setSelectionMode"
      />

      <ViewpointGeneralTab
        v-if="activeTab === 'general'"
        :draft="draft"
        :is-creating="isCreating"
        @update="Object.assign(draft, $event)"
      />
      <ViewpointScopeTab
        v-else-if="activeTab === 'scope'"
        v-model="draft.scope"
        :catalog="catalog"
      />
      <ViewpointQueryTab
        v-else-if="activeTab === 'query'"
        :draft="draft"
        :catalog="catalog"
        :is-creating="isCreating"
        :is-read-only="isReadOnly"
        @update:query="draft.query = $event"
        @issues="issues = $event"
      />
      <ViewpointPresentationTab
        v-else-if="activeTab === 'presentation'"
        v-model="draft.presentation"
        :catalog="catalog"
        :declared-derived-names="draft.query?.derived.filter((d) => d.name.length > 0).map((d) => d.name) ?? []"
      />

      <p
        v-if="saveError"
        class="error save-error"
      >
        {{ saveError }}
        <button
          type="button"
          class="retry-btn"
          @click="save"
        >
          ↻ Retry
        </button>
      </p>

      <div class="save-row">
        <button
          v-if="!isReadOnly"
          type="button"
          class="primary-btn"
          :disabled="saving || writeBlocked"
          @click="save"
        >
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
        <button
          v-if="!isCreating"
          type="button"
          class="save-as-btn"
          :disabled="saving || writeBlocked"
          title="Keep the current definition (including your unsaved changes) as a new engagement viewpoint — records fork lineage"
          @click="startSaveAs"
        >
          Save as…
        </button>
        <button
          v-if="forkedFromSlug"
          type="button"
          class="cancel-btn"
          :disabled="saving"
          title="Abandon this fork and return to the catalog without saving"
          @click="backToList()"
        >
          Cancel
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { padding: 20px 28px; max-width: 980px; }
.error { color: #991b1b; background: #fee2e2; padding: 8px 12px; border-radius: 6px; }
.save-error { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
.retry-btn { appearance: none; border: 1px solid #991b1b; border-radius: 6px; background: #fff; color: #991b1b; font-size: 12px; padding: 3px 10px; cursor: pointer; flex-shrink: 0; }
.retry-btn:hover { background: #fef2f2; }
.primary-btn { background: #6366f1; color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-weight: 600; cursor: pointer; margin-bottom: 12px; }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.save-as-btn {
  background: #fff; color: #4338ca; border: 1px solid #c7d2fe; border-radius: 7px;
  padding: 8px 16px; font-weight: 600; cursor: pointer; margin-bottom: 12px; margin-left: 8px;
}
.save-as-btn:hover:not(:disabled) { background: #eef2ff; }
.save-as-btn:disabled { opacity: .5; cursor: not-allowed; }
.save-row { margin-top: 20px; display: flex; align-items: center; }
.back-btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.back-btn:hover { border-color: #6366f1; color: #4338ca; }
.editor-topbar { display: flex; align-items: center; justify-content: space-between; }
.help-link { font-size: 12.5px; color: #6b7280; text-decoration: none; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 10px; }
.help-link:hover { color: #4338ca; border-color: #c7d2fe; }
.cancel-btn {
  appearance: none; background: #fff; color: #6b7280; border: 1px solid #d1d5db; border-radius: 7px;
  padding: 8px 16px; font-weight: 600; cursor: pointer; margin-bottom: 12px; margin-left: 8px;
}
.cancel-btn:hover:not(:disabled) { border-color: #9ca3af; color: #374151; }
</style>
