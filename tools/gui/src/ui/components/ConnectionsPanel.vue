<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { modelServiceKey } from '../keys'
import type {
  ConnectionRecord,
  ConnectionList,
  OntologyClassification,
  WriteHelp,
  AuthoringGuidance,
} from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { useQuery } from '../composables/useQuery'
import ConnectionAssociationsPanel from './ConnectionAssociationsPanel.vue'
import ConnectionAddForm from './ConnectionAddForm.vue'
import ConnectionEditForm from './ConnectionEditForm.vue'
import ConnectionRemoveModal from './ConnectionRemoveModal.vue'

const props = defineProps<{
  entityId: string
  entityType: string
  connections: ConnectionList
  direction: 'outgoing' | 'incoming' | 'symmetric'
  loading: boolean
  error: string | null
  readonly?: boolean
  adminMode?: boolean
}>()

const friendlyName = (id: string) => {
  const parts = id.split('.')
  return parts.length > 2 ? parts.slice(2).join(' ').replace(/-/g, ' ') : id
}

const emit = defineEmits<{
  refresh: []
}>()

const svc = inject(modelServiceKey)!

// ── Ontology ──────────────────────────────────────────────────────────────────

const ontologyQuery = useQuery<OntologyClassification, RepoError>()
const writeHelpQuery = useQuery<WriteHelp, RepoError>()
const guidanceQuery = useQuery<AuthoringGuidance, RepoError>()

const ontology = computed(() => ontologyQuery.data.value)

const prefixToType = computed((): Record<string, string> => {
  const catalog = writeHelpQuery.data.value?.entity_type_catalog
  if (!catalog) return {}
  return Object.fromEntries(
    Object.entries(catalog)
      .filter(([, info]) => info.prefix)
      .map(([artifactType, info]) => [info.prefix, artifactType])
  )
})

onMounted(() => {
  writeHelpQuery.run(svc.getWriteHelp())
  ontologyQuery.run(svc.getOntologyClassification(props.entityType))
  // The connection_types specialization block is independent of any entity-type filter
  // (see `_connection_type_guidance` in `type_guidance.py`) — filtering by this panel's own
  // entity type just keeps the accompanying entity_types payload small, matching the
  // ontologyQuery call just above.
  guidanceQuery.run(svc.getAuthoringGuidance({ entityTypes: [props.entityType] }))
})

watch(() => props.entityType, () => {
  ontologyQuery.run(svc.getOntologyClassification(props.entityType))
})

const permissibleTypes = computed((): string[] => {
  if (!ontology.value) return []
  const map = ontology.value[props.direction] as Record<string, string[]>
  return Object.keys(map).sort()
})

const symmetricConnTypes = computed((): Set<string> => {
  if (!ontology.value) return new Set()
  const types = new Set<string>()
  for (const conns of Object.values(ontology.value.symmetric)) {
    for (const ct of conns) types.add(ct)
  }
  return types
})

// ── Grouping ──────────────────────────────────────────────────────────────────

const artifactTypeFromId = (artifactId: string) => {
  const prefix = artifactId.split('@')[0] ?? ''
  return prefixToType.value[prefix] ?? prefix.toLowerCase()
}

const otherArtifactId = (c: ConnectionRecord) => {
  if (props.direction === 'incoming') return c.source
  if (props.direction === 'symmetric') return c.source === props.entityId ? c.target : c.source
  return c.target
}

const grouped = computed(() => {
  const groups: Record<string, ConnectionRecord[]> = {}
  const symTypes = symmetricConnTypes.value
  for (const c of props.connections) {
    const isSym = symTypes.has(c.conn_type)
    if (props.direction === 'symmetric' && !isSym) continue
    if (props.direction !== 'symmetric' && isSym) continue
    const otherId = otherArtifactId(c)
    const typePart = artifactTypeFromId(otherId)
    if (!groups[typePart]) groups[typePart] = []
    groups[typePart].push({ ...c })
  }
  return groups
})

const sectionKeys = computed((): string[] => {
  const all = new Set([...permissibleTypes.value, ...Object.keys(grouped.value)])
  return Array.from(all).sort()
})

const otherEnd = (c: ConnectionRecord) => otherArtifactId(c)

const otherEndName = (c: ConnectionRecord) => {
  if (props.direction === 'incoming') return c.source_name || friendlyName(c.source)
  if (props.direction === 'symmetric') {
    const otherId = otherEnd(c)
    if (otherId === c.source) return c.source_name || friendlyName(c.source)
    return c.target_name || friendlyName(c.target)
  }
  return c.target_name || friendlyName(c.target)
}

const titleLabel = computed(() => {
  if (props.direction === 'outgoing') return 'Outgoing'
  if (props.direction === 'incoming') return 'Incoming'
  return 'Symmetric'
})

// ── Association expand ───────────────────────────────────────────────────────

const expandedAssoc = ref<Set<string>>(new Set())
const editingConnection = ref<string | null>(null)

const toggleAssoc = (connId: string) => {
  const next = new Set(expandedAssoc.value)
  if (next.has(connId)) next.delete(connId)
  else next.add(connId)
  expandedAssoc.value = next
}

const toggleEdit = (connId: string) => {
  editingConnection.value = editingConnection.value === connId ? null : connId
}

// ── Add connection ─────────────────────────────────────────────────────────────

const addingFor = ref<string | null>(null)

const startAdd = (typeKey: string) => {
  addingFor.value = addingFor.value === typeKey ? null : typeKey
}
const onAdded = () => {
  addingFor.value = null
  emit('refresh')
}
const onEdited = () => {
  editingConnection.value = null
  emit('refresh')
}

// ── Remove connection ──────────────────────────────────────────────────────────

const removeModal = ref<InstanceType<typeof ConnectionRemoveModal> | null>(null)
</script>

<template>
  <div class="conn-panel">
    <h2 class="conn-title">
      {{ titleLabel }} connections
    </h2>

    <div
      v-if="loading"
      class="state-msg"
    >
      Loading...
    </div>
    <div
      v-else-if="error"
      class="state-msg state-msg--error"
    >
      {{ error }}
    </div>

    <template v-else>
      <template v-if="sectionKeys.length">
        <div
          v-for="typeKey in sectionKeys"
          :key="typeKey"
          class="type-group"
        >
          <div class="group-header">
            <span class="group-type-badge">{{ typeKey }}</span>
            <span class="group-count">{{ (grouped[typeKey] ?? []).length }}</span>
            <button
              v-if="!readonly"
              class="icon-btn add-btn"
              title="Add connection"
              @click="startAdd(typeKey)"
            >
              +
            </button>
          </div>

          <ul
            v-if="grouped[typeKey]?.length"
            class="conn-list"
          >
            <li
              v-for="c in grouped[typeKey]"
              :key="c.artifact_id"
              class="conn-item-wrap"
            >
              <div class="conn-item">
                <span class="conn-type-badge">{{ c.conn_type.replace('archimate-', '') }}</span>
                <span
                  v-if="c.specialization"
                  class="conn-spec-badge"
                >«{{ c.specialization }}»</span>
                <span
                  v-if="c.src_multiplicity || c.tgt_multiplicity"
                  class="conn-mult-badge"
                >{{ c.src_multiplicity ? `[${c.src_multiplicity}]` : '' }}→{{ c.tgt_multiplicity ? `[${c.tgt_multiplicity}]` : '' }}</span>
                <RouterLink
                  :to="{ path: '/entity', query: { id: otherEnd(c) } }"
                  class="conn-target"
                >
                  {{ otherEndName(c) }}
                </RouterLink>
                <span
                  v-if="c.content_text?.trim()"
                  class="conn-info-wrap"
                >
                  <span
                    class="conn-info-btn"
                    tabindex="0"
                  >ⓘ</span>
                  <span class="conn-info-tip">{{ c.content_text.trim() }}</span>
                </span>
                <button
                  v-if="!readonly && !adminMode"
                  class="icon-btn edit-btn"
                  :class="{ 'edit-btn--active': editingConnection === c.artifact_id }"
                  :title="editingConnection === c.artifact_id ? 'Close relationship editor' : 'Edit relationship'"
                  @click="toggleEdit(c.artifact_id)"
                >
                  ✎
                </button>
                <button
                  v-if="!readonly"
                  class="icon-btn assoc-btn"
                  :class="{ 'assoc-btn--active': expandedAssoc.has(c.artifact_id) }"
                  :title="expandedAssoc.has(c.artifact_id) ? 'Hide associations' : 'Associations'"
                  @click="toggleAssoc(c.artifact_id)"
                >
                  {{ (c.associated_entities?.length ?? 0) > 0 ? `⊕${c.associated_entities!.length}` : '⊕' }}
                </button>
                <button
                  v-if="!readonly"
                  class="icon-btn remove-btn"
                  title="Remove connection"
                  @click="removeModal?.requestRemove(c)"
                >
                  ×
                </button>
              </div>

              <ConnectionAssociationsPanel
                v-if="!readonly && expandedAssoc.has(c.artifact_id)"
                :connection="c"
                @refresh="emit('refresh')"
              />
              <ConnectionEditForm
                v-if="!readonly && !adminMode && editingConnection === c.artifact_id"
                :connection="c"
                :guidance="guidanceQuery.data.value"
                @saved="onEdited"
                @cancel="editingConnection = null"
              />
            </li>
          </ul>

          <ConnectionAddForm
            v-if="addingFor === typeKey"
            :entity-id="entityId"
            :entity-type="entityType"
            :type-key="typeKey"
            :direction="direction"
            :admin-mode="adminMode"
            :symmetric-conn-types="symmetricConnTypes"
            :guidance="guidanceQuery.data.value"
            @added="onAdded"
            @cancel="addingFor = null"
          />
        </div>
      </template>

      <!-- Fallback when no ontology data yet and no connections -->
      <div
        v-else
        class="state-msg"
      >
        None
      </div>
    </template>

    <ConnectionRemoveModal
      ref="removeModal"
      :admin-mode="adminMode"
      @removed="emit('refresh')"
    />
  </div>
</template>

<style scoped src="./ConnectionsPanel.css"></style>
