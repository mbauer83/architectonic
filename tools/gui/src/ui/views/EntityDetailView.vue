<script setup lang="ts">
import { inject, onMounted, provide, ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey, toastKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { entityEditFormKey, useEntityEditForm } from '../composables/useEntityEditForm'
import ConnectionsPanel from '../components/ConnectionsPanel.vue'
import ArtifactReferenceInput from '../components/ArtifactReferenceInput.vue'
import AssuranceLens from '../components/AssuranceLens.vue'
import DerivedSecurityAttributesPanel from '../components/DerivedSecurityAttributesPanel.vue'
import SignalIngestPanel from '../components/SignalIngestPanel.vue'
import EntityDetailHeader from '../components/EntityDetailHeader.vue'
import EntityEditFormCard from '../components/EntityEditFormCard.vue'
import EntityDeletePanel from '../components/EntityDeletePanel.vue'
import EntityDocumentReferences from '../components/EntityDocumentReferences.vue'
import type { EntityContext } from '../../domain'
import type { NotFoundError } from '../../domain'
import type { MarkdownError } from '../../application/MarkdownService'
import type { RepoError } from '../../ports/ModelRepository'
import { readErrorMessage } from '../lib/errors'

const svc = inject(modelServiceKey)!
const addToast = inject(toastKey)!
const router = useRouter()
const adminMode = ref(false)
const route = useRoute()

const entityId = computed(() => (route.query.id as string | undefined) ?? '')
/** Bumped after an ingest so the derived-attributes panel re-reads: it shows the
 *  ACTIVE snapshot, which a successful ingest has just replaced. */
const signalsVersion = ref(0)

const browseQuery = computed(() => {
  const q: Record<string, string> = {}
  const { domain, view, type } = route.query
  if (domain) q.domain = domain as string
  if (view) q.view = view as string
  if (type) q.type = type as string
  return q
})
const backTo = computed(() => ({
  path: '/entities',
  query: { ...browseQuery.value, ...(detail.value?.is_global ? { tier: 'enterprise' } : {}) },
}))

const context = useQuery<EntityContext, RepoError | NotFoundError | MarkdownError>()
const detail = computed(() => context.data.value?.entity ?? null)
const outgoing = computed(() => context.data.value?.connections.outbound ?? [])
const incoming = computed(() => context.data.value?.connections.inbound ?? [])
const symmetric = computed(() => context.data.value?.connections.symmetric ?? [])
const documentReferences = computed(() => detail.value?.referenced_in_documents ?? [])

const load = () => {
  if (!entityId.value) return
  context.run(svc.getEntityContext(entityId.value))
}

onMounted(() => {
  void Effect.runPromise(svc.getServerInfo())
    .then((info) => { adminMode.value = info.admin_mode })
    .catch((reason: unknown) => { edit.editError = readErrorMessage(reason) })
  load()
})
watch(entityId, load)

const isGlobalEntity = computed(() => detail.value?.is_global ?? false)
// Use admin endpoint when editing a global entity in admin mode
const editFn = computed(() => (isGlobalEntity.value && adminMode.value) ? svc.adminEditEntity : svc.editEntity)

const edit = useEntityEditForm({
  svc,
  entityId,
  detail,
  editFn,
  onSaved: (newArtifactId) => {
    addToast('Entity saved')
    if (newArtifactId && newArtifactId !== entityId.value) {
      void router.replace({ path: '/entity', query: { id: newArtifactId, ...browseQuery.value } })
    } else {
      load()
    }
  },
})
provide(entityEditFormKey, edit)

const deletePanel = ref<InstanceType<typeof EntityDeletePanel> | null>(null)
const executeDelete = () => { void router.push(backTo.value) }
</script>

<template>
  <div>
    <EntityDetailHeader
      v-if="detail"
      :detail="detail"
      :entity-id="entityId"
      :back-to="backTo"
      :admin-mode="adminMode"
      :is-global-entity="isGlobalEntity"
      @delete="deletePanel?.requestDelete()"
    />

    <div
      v-if="context.loading.value"
      class="state-msg"
    >
      Loading...
    </div>
    <div
      v-else-if="context.errorMessage.value"
      class="state-msg state-msg--error"
    >
      {{ context.errorMessage.value }}
    </div>

    <template v-else-if="detail">
      <EntityEditFormCard
        v-if="edit.editing"
        @open-reference-picker="edit.openReferencePicker($event)"
      />

      <div
        v-else-if="detail?.content_html"
        class="card content-card"
      >
        <div
          class="markdown-body"
          v-html="detail.content_html"
        />
      </div>

      <EntityDeletePanel
        v-if="!isGlobalEntity || adminMode"
        ref="deletePanel"
        :entity-id="entityId"
        :is-global-entity="isGlobalEntity"
        :admin-mode="adminMode"
        @deleted="executeDelete"
      />

      <EntityDocumentReferences
        v-if="documentReferences.length"
        :references="documentReferences"
      />

      <!-- Connections: [INCOMING] [SYMMETRIC] [OUTGOING] on wide screens -->
      <div class="connections-section">
        <ConnectionsPanel
          :entity-id="entityId"
          :entity-type="detail.artifact_type"
          :connections="incoming"
          direction="incoming"
          :loading="context.loading.value"
          :error="context.errorMessage.value"
          :readonly="isGlobalEntity && !adminMode"
          :admin-mode="isGlobalEntity && adminMode"
          @refresh="load"
        />
        <ConnectionsPanel
          :entity-id="entityId"
          :entity-type="detail.artifact_type"
          :connections="symmetric"
          direction="symmetric"
          :loading="context.loading.value"
          :error="context.errorMessage.value"
          :readonly="isGlobalEntity && !adminMode"
          :admin-mode="isGlobalEntity && adminMode"
          @refresh="load"
        />
        <ConnectionsPanel
          :entity-id="entityId"
          :entity-type="detail.artifact_type"
          :connections="outgoing"
          direction="outgoing"
          :loading="context.loading.value"
          :error="context.errorMessage.value"
          :readonly="isGlobalEntity && !adminMode"
          :admin-mode="isGlobalEntity && adminMode"
          @refresh="load"
        />
      </div>

      <!-- Assurance lens: shows assurance findings that concern this entity (hidden when locked) -->
      <AssuranceLens
        v-if="entityId"
        :artifact-id="entityId"
      />

      <!-- Derived security attributes (read-only; absent when locked/unanchored) -->
      <DerivedSecurityAttributesPanel
        v-if="entityId"
        :key="`derived-${signalsVersion}`"
        :artifact-id="entityId"
      />

      <!-- Ingest an SBOM for this element (only for admissible anchor types) -->
      <SignalIngestPanel
        v-if="entityId"
        :artifact-id="entityId"
        :entity-type="detail?.artifact_type"
        @ingested="signalsVersion++"
      />

      <div
        v-if="edit.showReferencePicker"
        class="overlay"
        @click.self="edit.showReferencePicker = false"
      >
        <ArtifactReferenceInput
          :current-path="detail?.path"
          :fixed-kinds="['diagram', 'document']"
          @insert="edit.insertReference($event)"
          @close="edit.showReferencePicker = false"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.state-msg { color: #6b7280; padding: 4px 0; }
.state-msg--error { color: #dc2626; }

.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.content-card { padding: 16px 20px; margin-bottom: 24px; overflow-x: auto; }

.markdown-body :deep(p) { margin: 1rem 0 1.7rem 0; }
.markdown-body :deep(ul) { padding-left: 1.5rem; }
.markdown-body :deep(table) { inline-size: 100%; border-collapse: collapse; margin-block: 2rem; min-inline-size: max-content; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding-inline: 1.25rem; padding-block: 0.75rem; text-align: start; border-bottom: 1px solid var(--border-color, #eee); }

/* Connections — [INCOMING] [SYMMETRIC] [OUTGOING] */
.connections-section { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
@media (max-width: 1000px) { .connections-section { grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px) { .connections-section { grid-template-columns: 1fr; } }
.overlay {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.48);
  display: flex; align-items: center; justify-content: center; padding: 24px; z-index: 50;
}
</style>
