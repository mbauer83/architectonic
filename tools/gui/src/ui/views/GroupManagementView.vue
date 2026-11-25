<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { metaOntologyOptionsForModules } from '../lib/domains'
import type { GroupAxis, GroupList, ModuleSummary } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import EntityGroupNavTree from '../components/EntityGroupNavTree.vue'
import GroupSelector from '../components/GroupSelector.vue'

type Axis = GroupAxis

const props = defineProps<{ axis: Axis }>()

const svc = inject(modelServiceKey)!
const router = useRouter()
const groupsState = useQuery<GroupList, RepoError>()
const modulesState = useQuery<readonly ModuleSummary[], RepoError>()

const STORAGE_KEYS: Record<Axis, string> = {
  'model-project': 'arch_group_model-project',
  'diagram-collection': 'arch_group_diagram-collection',
  'document-collection': 'arch_group_document-collection',
  'analysis-collection': 'arch_group_analysis-collection',
}
const BROWSE_PATHS: Record<Axis, string> = {
  'model-project': '/entities',
  'diagram-collection': '/diagrams',
  'document-collection': '/documents',
  'analysis-collection': '/assurance/analyses',
}
const AXIS_LABELS: Record<Axis, { title: string; singular: string; filterLabel: string }> = {
  'model-project': { title: 'Model Projects', singular: 'project', filterLabel: 'Framework' },
  'diagram-collection': { title: 'Diagram Collections', singular: 'collection', filterLabel: 'Type Filter' },
  'document-collection': { title: 'Document Collections', singular: 'collection', filterLabel: 'Type Filter' },
  'analysis-collection': { title: 'Analysis Collections', singular: 'collection', filterLabel: 'Type Filter' },
}
const REGISTRY_KEY: Record<Axis, keyof GroupList> = {
  'model-project': 'model-projects',
  'diagram-collection': 'diagram-collections',
  'document-collection': 'document-collections',
  'analysis-collection': 'analysis-collections',
}

const groups = computed(() => groupsState.data.value?.[REGISTRY_KEY[props.axis]] ?? [])
const metaOntologyOptions = computed(() => metaOntologyOptionsForModules(modulesState.data.value ?? undefined))
const showArchived = ref(false)
const visibleGroups = computed(() => groups.value.filter(g => showArchived.value || !g.archived))

const sidebarGroups = computed(() =>
  groups.value.map(g => ({ slug: g.slug, name: g.name, archived: g.archived ?? false, meta_ontology: g.meta_ontology ?? '' }))
)

const onSidebarSelectGroup = (slug: string) => {
  if (!slug) return
  localStorage.setItem(STORAGE_KEYS[props.axis], slug)
  void router.push({ path: BROWSE_PATHS[props.axis], query: { group: slug } })
}
const availableTypes = ref<string[]>([])

const editSlug = ref<string | null>(null)
const editName = ref('')
const editDescription = ref('')
const editMetaOntology = ref('')
const editTypeFilter = ref<string[]>([])
const editError = ref('')
const editBusy = ref(false)

const createMode = ref(false)
const newName = ref('')
const newSlug = ref('')
const newDescription = ref('')
const newMetaOntology = ref('')
const newTypeFilter = ref<string[]>([])
const createError = ref('')
const createBusy = ref(false)

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

const openEdit = (g: { slug: string; name: string; description?: string; meta_ontology?: string; type_filter?: readonly string[] }) => {
  editSlug.value = g.slug
  editName.value = g.name
  editDescription.value = g.description ?? ''
  editMetaOntology.value = g.meta_ontology ?? ''
  editTypeFilter.value = [...(g.type_filter ?? [])]
  editError.value = ''
}
const cancelEdit = () => { editSlug.value = null; editError.value = '' }

const saveEdit = async () => {
  if (!editSlug.value) return
  editBusy.value = true; editError.value = ''
  try {
    await Effect.runPromise(svc.updateGroup(props.axis, editSlug.value, {
      name: editName.value,
      description: editDescription.value,
      meta_ontology: showMetaOntology.value ? editMetaOntology.value : undefined,
      type_filter: showTypeFilter.value ? editTypeFilter.value : null,
    }))
    cancelEdit()
    loadGroups()
  } catch (e) { editError.value = String(e) }
  finally { editBusy.value = false }
}

/**
 * Archive / unarchive / delete lifecycle. Archiving a group that still has members and any
 * delete require typing the slug — mirroring the backend's typed-confirm contract instead of
 * hiding it behind an auto-filled parameter. Delete is offered only for empty groups (the
 * cascade path for populated projects stays MCP-only); analysis collections get no delete —
 * their members live in the (possibly locked) assurance store, so emptiness is unknowable here.
 */
const lifecycleSlug = ref<string | null>(null)
const lifecycleAction = ref<'archive' | 'delete' | null>(null)
const lifecycleConfirmText = ref('')
const lifecycleError = ref('')
const lifecycleBusy = ref(false)

const memberCount = (g: { member_count?: number }) => g.member_count ?? 0
const canDelete = (g: { slug: string; member_count?: number }) =>
  props.axis !== 'analysis-collection' && g.slug !== 'uncategorized' && memberCount(g) === 0
const canArchive = (g: { slug: string; archived?: boolean }) =>
  g.slug !== 'uncategorized' && !g.archived

const needsTypedConfirm = computed(() => {
  const g = groups.value.find(x => x.slug === lifecycleSlug.value)
  return lifecycleAction.value === 'delete' || (g !== undefined && memberCount(g) > 0)
})

const openLifecycle = (slug: string, action: 'archive' | 'delete') => {
  lifecycleSlug.value = slug
  lifecycleAction.value = action
  lifecycleConfirmText.value = ''
  lifecycleError.value = ''
}
const cancelLifecycle = () => { lifecycleSlug.value = null; lifecycleAction.value = null }

const confirmLifecycle = async () => {
  const slug = lifecycleSlug.value
  const action = lifecycleAction.value
  if (!slug || !action) return
  if (needsTypedConfirm.value && lifecycleConfirmText.value !== slug) {
    lifecycleError.value = `Type "${slug}" to confirm.`
    return
  }
  lifecycleBusy.value = true; lifecycleError.value = ''
  try {
    if (action === 'archive') {
      await Effect.runPromise(svc.archiveGroup(props.axis, slug, { confirm: slug }))
    } else {
      await Effect.runPromise(svc.deleteGroup(props.axis, slug, slug))
    }
    cancelLifecycle()
    loadGroups()
  } catch (e) { lifecycleError.value = String(e) }
  finally { lifecycleBusy.value = false }
}

const unarchive = async (slug: string) => {
  lifecycleBusy.value = true
  try {
    await Effect.runPromise(svc.unarchiveGroup(props.axis, slug))
    loadGroups()
  } catch (e) { lifecycleError.value = String(e); lifecycleSlug.value = slug; lifecycleAction.value = null }
  finally { lifecycleBusy.value = false }
}

const submitCreate = async () => {
  if (!newSlug.value || !newName.value) return
  createBusy.value = true; createError.value = ''
  try {
    await Effect.runPromise(svc.createGroup({
      kind: props.axis,
      slug: newSlug.value,
      name: newName.value,
      description: newDescription.value,
      meta_ontology: showMetaOntology.value ? newMetaOntology.value : undefined,
      type_filter: showTypeFilter.value ? newTypeFilter.value : undefined,
    }))
    createMode.value = false
    newName.value = ''; newSlug.value = ''; newDescription.value = ''
    newMetaOntology.value = ''; newTypeFilter.value = []
    loadGroups()
  } catch (e) { createError.value = String(e) }
  finally { createBusy.value = false }
}

const toggleType = (target: string[], type: string) => {
  const idx = target.indexOf(type)
  idx === -1 ? target.push(type) : target.splice(idx, 1)
}

const browseTo = () => {
  localStorage.setItem(STORAGE_KEYS[props.axis], '')
  void router.push(BROWSE_PATHS[props.axis])
}

const browseToGroup = (slug: string) => {
  localStorage.setItem(STORAGE_KEYS[props.axis], slug)
  void router.push({ path: BROWSE_PATHS[props.axis], query: { group: slug } })
}

const loadGroups = () => groupsState.run(svc.listGroups(props.axis))

onMounted(async () => {
  loadGroups()
  modulesState.run(svc.listModules())
  if (props.axis === 'diagram-collection') {
    const kinds = await Effect.runPromise(svc.listDiagramTypes()).catch(() => [])
    availableTypes.value = kinds.map((k: { key: string }) => k.key)
  } else if (props.axis === 'document-collection') {
    const types = await Effect.runPromise(svc.listDocumentTypes()).catch(() => [])
    availableTypes.value = types.map((t: { doc_type: string }) => t.doc_type)
  }
})

const showMetaOntology = computed(() => props.axis === 'model-project')
const showTypeFilter = computed(() => props.axis !== 'model-project')
const label = computed(() => AXIS_LABELS[props.axis])

</script>

<template>
  <div class="outer-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2 class="sidebar-title">
          {{ axis === 'model-project' ? 'Project' : 'Collection' }}
        </h2>
      </div>
      <EntityGroupNavTree
        v-if="axis === 'model-project'"
        :groups="sidebarGroups"
        active-group=""
        active-domain=""
        :manageable="false"
        :modules="modulesState.data.value ?? undefined"
        axis="model-project"
        @update:active-group="onSidebarSelectGroup"
        @navigate-to-groups="() => {}"
      />
      <GroupSelector
        v-else
        :groups="sidebarGroups"
        model-value=""
        :manageable="false"
        :axis="axis"
        @update:model-value="onSidebarSelectGroup"
        @navigate-to-groups="() => {}"
      />
    </aside>
    <div class="mgmt-page">
      <div class="page-header">
        <div>
          <h1 class="page-title">
            {{ label.title }}
          </h1>
          <p class="subtitle">
            Manage groupings, metadata, and {{ showMetaOntology ? 'ontology restrictions' : 'type filters' }}.
          </p>
        </div>
        <button
          class="browse-btn"
          @click="browseTo"
        >
          Browse {{ label.title }} →
        </button>
      </div>

      <div
        v-if="groupsState.loading.value"
        class="state-msg"
      >
        Loading…
      </div>
      <div
        v-else-if="groupsState.errorMessage.value"
        class="state-msg error"
      >
        {{ groupsState.errorMessage.value }}
      </div>

      <template v-else>
        <div class="toolbar">
          <button
            class="create-btn"
            @click="createMode = !createMode"
          >
            {{ createMode ? '✕ Cancel' : '+ New ' + label.singular }}
          </button>
          <button
            class="archived-btn"
            :class="{ active: showArchived }"
            @click="showArchived = !showArchived"
          >
            {{ showArchived ? '− archived' : '+ archived' }}
          </button>
        </div>

        <div
          v-if="createMode"
          class="create-form card"
        >
          <div class="form-row">
            <label class="field">Name<input
              v-model="newName"
              class="field-input"
              @input="newSlug = slugify(newName)"
            ></label>
            <label class="field">Slug<input
              v-model="newSlug"
              class="field-input"
            ></label>
            <label
              v-if="showMetaOntology"
              class="field"
            >
              Framework
              <select
                v-model="newMetaOntology"
                class="field-input"
              >
                <option
                  v-for="o in metaOntologyOptions"
                  :key="o.value"
                  :value="o.value"
                >{{ o.label }}</option>
              </select>
            </label>
          </div>
          <label class="field">Description<input
            v-model="newDescription"
            class="field-input"
          ></label>
          <div
            v-if="showTypeFilter && availableTypes.length > 0"
            class="field"
          >
            {{ label.filterLabel }} (leave empty for all)
            <div class="type-checks">
              <label
                v-for="t in availableTypes"
                :key="t"
                class="type-check"
              >
                <input
                  type="checkbox"
                  :checked="newTypeFilter.includes(t)"
                  @change="toggleType(newTypeFilter, t)"
                > {{ t }}
              </label>
            </div>
          </div>
          <div
            v-if="createError"
            class="err"
          >
            {{ createError }}
          </div>
          <div class="form-actions">
            <button
              class="btn--primary"
              :disabled="createBusy || !newSlug || !newName"
              @click="submitCreate"
            >
              Create
            </button>
          </div>
        </div>

        <div class="card table-card">
          <table class="groups-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug / ID</th>
                <th>{{ label.filterLabel }}</th>
                <th>Description</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr v-if="visibleGroups.length === 0">
                <td
                  colspan="5"
                  class="empty"
                >
                  No {{ label.singular }}s yet.
                </td>
              </tr>
              <template
                v-for="g in visibleGroups"
                :key="g.slug"
              >
                <tr
                  v-if="editSlug !== g.slug"
                  :class="{ archived: g.archived }"
                >
                  <td class="td-name">
                    <button
                      class="name-link"
                      @click="browseToGroup(g.slug)"
                    >
                      {{ g.name }}
                    </button>
                    <span
                      v-if="g.archived"
                      class="arch-badge"
                    >archived</span>
                    <span
                      v-if="g.default"
                      class="default-badge"
                    >default</span>
                  </td>
                  <td class="td-meta">
                    <span class="mono">{{ g.slug }}</span>
                    <span class="id-text">{{ g.id }}</span>
                  </td>
                  <td>
                    <span
                      v-if="showMetaOntology && g.meta_ontology"
                      class="mo-badge"
                    >{{ metaOntologyOptions.find(o => o.value === g.meta_ontology)?.label ?? g.meta_ontology }}</span>
                    <span
                      v-else-if="showTypeFilter && g.type_filter && g.type_filter.length > 0"
                      class="tf-badge"
                    >{{ g.type_filter.join(', ') }}</span>
                    <span
                      v-else
                      class="none-text"
                    >—</span>
                  </td>
                  <td class="td-desc">
                    {{ g.description || '—' }}
                  </td>
                  <td class="td-actions">
                    <template v-if="lifecycleSlug === g.slug">
                      <div
                        v-if="lifecycleError"
                        class="err"
                      >
                        {{ lifecycleError }}
                      </div>
                      <template v-if="lifecycleAction">
                        <input
                          v-if="needsTypedConfirm"
                          v-model="lifecycleConfirmText"
                          class="field-input confirm-input"
                          :placeholder="`Type ${g.slug} to confirm`"
                        >
                        <button
                          class="row-btn row-btn--danger"
                          :disabled="lifecycleBusy"
                          @click="confirmLifecycle"
                        >
                          {{ lifecycleAction === 'delete' ? 'Delete' : 'Archive' }}
                        </button>
                        <button
                          class="row-btn"
                          @click="cancelLifecycle"
                        >
                          Cancel
                        </button>
                      </template>
                    </template>
                    <template v-else>
                      <button
                        class="row-btn"
                        @click="openEdit(g)"
                      >
                        Edit
                      </button>
                      <button
                        v-if="canArchive(g)"
                        class="row-btn"
                        :disabled="lifecycleBusy"
                        @click="openLifecycle(g.slug, 'archive')"
                      >
                        Archive
                      </button>
                      <button
                        v-if="g.archived && g.slug !== 'uncategorized'"
                        class="row-btn"
                        :disabled="lifecycleBusy"
                        @click="unarchive(g.slug)"
                      >
                        Unarchive
                      </button>
                      <button
                        v-if="canDelete(g)"
                        class="row-btn row-btn--danger"
                        :disabled="lifecycleBusy"
                        @click="openLifecycle(g.slug, 'delete')"
                      >
                        Delete
                      </button>
                    </template>
                  </td>
                </tr>
                <tr
                  v-else
                  class="edit-row"
                >
                  <td>
                    <input
                      v-model="editName"
                      class="field-input"
                      placeholder="Name"
                    >
                  </td>
                  <td class="td-meta">
                    <span class="mono">{{ g.slug }}</span>
                  </td>
                  <td>
                    <select
                      v-if="showMetaOntology"
                      v-model="editMetaOntology"
                      class="field-input"
                    >
                      <option
                        v-for="o in metaOntologyOptions"
                        :key="o.value"
                        :value="o.value"
                      >
                        {{ o.label }}
                      </option>
                    </select>
                    <div
                      v-else-if="showTypeFilter && availableTypes.length > 0"
                      class="type-checks"
                    >
                      <label
                        v-for="t in availableTypes"
                        :key="t"
                        class="type-check"
                      >
                        <input
                          type="checkbox"
                          :checked="editTypeFilter.includes(t)"
                          @change="toggleType(editTypeFilter, t)"
                        > {{ t }}
                      </label>
                    </div>
                    <span
                      v-else
                      class="none-text"
                    >—</span>
                  </td>
                  <td>
                    <input
                      v-model="editDescription"
                      class="field-input"
                      placeholder="Description"
                    >
                  </td>
                  <td class="td-actions">
                    <div
                      v-if="editError"
                      class="err"
                    >
                      {{ editError }}
                    </div>
                    <button
                      class="row-btn row-btn--primary"
                      :disabled="editBusy"
                      @click="saveEdit"
                    >
                      Save
                    </button>
                    <button
                      class="row-btn"
                      @click="cancelEdit"
                    >
                      Cancel
                    </button>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.outer-layout { display: flex; gap: 24px; align-items: flex-start; }
.sidebar { width: 190px; flex-shrink: 0; padding-top: 4px; }
.sidebar-header { margin-bottom: 6px; }
.sidebar-title {
  font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.mgmt-page { flex: 1; min-width: 0; max-width: 860px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 600; }
.subtitle { color: var(--muted); font-size: 13px; margin-top: 2px; }
.browse-btn { padding: 8px 16px; background: var(--accent); color: var(--on-accent); border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap; }
.browse-btn:hover { background: var(--accent-strong); }
.state-msg { color: var(--muted); }
.error { color: var(--danger); }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.create-btn { padding: 7px 14px; background: var(--ok); color: var(--on-accent); border: none; border-radius: 6px; font-size: 13px; cursor: pointer; }
.create-btn:hover { background: var(--ok); }
.archived-btn { padding: 5px 10px; border: 1px dashed var(--border-strong); border-radius: 4px; background: transparent; font-size: 12px; color: var(--muted); cursor: pointer; }
.archived-btn.active { color: var(--accent); border-color: var(--accent); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
.create-form { padding: 16px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; gap: 12px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; min-width: 140px; }
.field-input { padding: 6px 8px; border: 1px solid var(--border-strong); border-radius: 4px; font-size: 13px; }
.form-actions { display: flex; justify-content: flex-end; }
.type-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.type-check { display: flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--text-2); cursor: pointer; white-space: nowrap; }
.table-card { overflow: hidden; }
.groups-table { width: 100%; border-collapse: collapse; }
.groups-table th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; padding: 10px 14px; background: var(--hover); border-bottom: 1px solid var(--border); }
.groups-table td { padding: 10px 14px; border-bottom: 1px solid var(--hair); font-size: 13px; vertical-align: middle; }
.groups-table tr:last-child td { border-bottom: 0; }
.groups-table tr:hover td { background: var(--hover); }
.groups-table tr.archived td { opacity: 0.6; }
.groups-table tr.edit-row td { background: var(--info-soft); }
.td-name { font-weight: 500; }
.name-link { background: none; border: none; padding: 0; font: inherit; font-weight: 500; color: var(--accent); cursor: pointer; text-align: left; }
.name-link:hover { text-decoration: underline; }
.td-meta { display: flex; flex-direction: column; gap: 2px; }
.td-desc { color: var(--muted); max-width: 200px; }
.td-actions { white-space: nowrap; display: flex; gap: 6px; align-items: center; }
.mono { font-family: monospace; font-size: 12px; }
.id-text { font-size: 10px; color: var(--faint); font-family: monospace; }
.arch-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; background: var(--soft); color: var(--muted); border-radius: 3px; font-size: 10px; font-weight: 600; }
.default-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; background: var(--type-soft); color: var(--type-text); border-radius: 3px; font-size: 10px; font-weight: 600; }
.mo-badge { padding: 2px 8px; background: var(--violet-soft); color: var(--violet-text); border-radius: 4px; font-size: 11px; font-weight: 500; }
.tf-badge { padding: 2px 8px; background: var(--info-soft); color: var(--info-text); border-radius: 4px; font-size: 11px; font-weight: 500; }
.none-text { color: var(--faint); }
.empty { text-align: center; color: var(--faint); padding: 20px; }
.row-btn { padding: 4px 10px; border: 1px solid var(--border-strong); border-radius: 4px; background: var(--surface); cursor: pointer; font-size: 12px; }
.row-btn--primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
.row-btn--danger { color: var(--danger); border-color: var(--danger-border); }
.row-btn--danger:hover { background: var(--danger-soft); }
.confirm-input { max-width: 180px; font-size: 12px; margin-right: 6px; }
.row-btn--primary:hover:not(:disabled) { background: var(--accent-strong); }
.row-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.err { font-size: 11px; color: var(--danger); }
.btn--primary { background: var(--accent); color: var(--on-accent); border: none; border-radius: 4px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.btn--primary:hover:not(:disabled) { background: var(--accent-strong); }
.btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
