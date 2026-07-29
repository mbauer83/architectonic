<script setup lang="ts">
import type { DiagramTypeUiConfig, EntityDisplayInfo } from '../../../domain'
import { Effect } from 'effect'
import ClassifierCard from './ClassifierCard.vue'
import GeneralizationSetCard from './GeneralizationSetCard.vue'
import RelationList from './RelationList.vue'
import { useDatatypeModel } from './useDatatypeModel'
import type { Attribute, Classifier, DtConn, GeneralizationSet } from './useDatatypeModel'
import type { CatalogClassifier } from './ClassifierCard.helpers'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { modelServiceKey } from '../../keys'

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
  diagramId?: string
}>()
const emit = defineEmits<{
  diagramEntitiesChange: [patch: Record<string, unknown>]
}>()

const {
  classifiers, generalizationSets, connections,
  addClassifier, removeClassifier, updateClassifier,
  addAttribute, removeAttribute, updateAttribute,
  addLiteral, removeLiteral, updateLiteral,
  addGeneralizationSet, removeGeneralizationSet, updateGeneralizationSet,
  addConnection, removeConnection, updateConnection,
} = useDatatypeModel(
  () => props.diagramEntities,
  (patch) => emit('diagramEntitiesChange', patch),
)

const svc = inject(modelServiceKey)!
const primitiveTypes = computed(() => props.uiConfig.primitive_types ?? [])
const catalogClassifiers = ref<CatalogClassifier[]>([])
const usageCounts = ref<Record<string, number>>({})

async function loadTypes() {
  const result = await Effect.runPromise(svc.getDatatypeTypes({
    limit: 500,
    diagramId: props.diagramId || undefined,
  })).catch(() => null)
  if (!result) return
  catalogClassifiers.value = [...result.classifiers]
}

async function refreshUsageCounts() {
  const ids = classifiers.value.map((classifier) => classifier.id)
  const entries = await Promise.all(ids.map(async (id) => {
    const result = await Effect.runPromise(svc.getDatatypeTypeUsages(id)).catch(() => null)
    return [id, result?.usages.length ?? 0] as const
  }))
  usageCounts.value = Object.fromEntries(entries)
}

async function createClassifier(attrOwnerId?: string, attrIndex?: number) {
  const allocated = await Effect.runPromise(svc.allocateDiagramEntityId({
    owner_kind: 'diagram',
    diagram_type: 'datatype',
    entity_type: 'classifier',
    name_hint: 'Classifier',
  })).catch(() => null)
  if (!allocated) return
  addClassifier(
    allocated.id,
    'Classifier',
    attrOwnerId !== undefined && attrIndex !== undefined
      ? { classifierId: attrOwnerId, attrIndex }
      : undefined,
  )
}

async function createGeneralizationSet() {
  const allocated = await Effect.runPromise(svc.allocateDiagramEntityId({
    owner_kind: 'diagram',
    diagram_type: 'datatype',
    entity_type: 'generalization_set',
    name_hint: 'Generalization set',
  })).catch(() => null)
  if (!allocated) return
  addGeneralizationSet(allocated.id, 'Generalization set')
}

onMounted(() => {
  void loadTypes()
  void refreshUsageCounts()
})
watch(
  () => classifiers.value.map((classifier) => classifier.id).join('|'),
  () => { void refreshUsageCounts() },
)
</script>

<template>
  <div class="dte">
    <section class="dte-section">
      <div class="dte-hdr">
        <span class="dte-title">Classifiers</span>
        <button
          class="dte-add-btn"
          type="button"
          @click="createClassifier()"
        >
          + Classifier
        </button>
      </div>
      <div
        v-if="!classifiers.length"
        class="dte-empty"
      >
        Add classifiers to build the diagram.
      </div>
      <ClassifierCard
        v-for="cls in classifiers"
        :key="cls.id"
        :classifier="cls"
        :primitive-types="primitiveTypes"
        :classifiers="classifiers"
        :catalog-classifiers="catalogClassifiers"
        :diagram-id="diagramId ?? ''"
        :usage-count="usageCounts[cls.id] ?? 0"
        @update="(patch: Partial<Classifier>) => updateClassifier(cls.id, patch)"
        @remove="removeClassifier(cls.id)"
        @add-attr="addAttribute(cls.id)"
        @remove-attr="(i: number) => removeAttribute(cls.id, i)"
        @update-attr="(i: number, patch: Partial<Attribute>) => updateAttribute(cls.id, i, patch)"
        @add-literal="addLiteral(cls.id)"
        @remove-literal="(i: number) => removeLiteral(cls.id, i)"
        @update-literal="(i: number, val: string) => updateLiteral(cls.id, i, val)"
        @new-classifier="(i: number) => createClassifier(cls.id, i)"
      />
    </section>

    <section class="dte-section">
      <RelationList
        :classifiers="classifiers"
        :connections="connections"
        :generalization-sets="generalizationSets"
        @add-conn="(src: string, tgt: string) => addConnection(src, tgt)"
        @remove-conn="(id: string) => removeConnection(id)"
        @update-conn="(id: string, patch: Partial<DtConn>) => updateConnection(id, patch)"
      />
    </section>

    <section class="dte-section">
      <GeneralizationSetCard
        :sets="generalizationSets"
        @add="createGeneralizationSet"
        @remove="(id: string) => removeGeneralizationSet(id)"
        @update="(id: string, patch: Partial<GeneralizationSet>) => updateGeneralizationSet(id, patch)"
      />
    </section>
  </div>
</template>

<style scoped>
.dte { display: flex; flex-direction: column; gap: 12px; }
.dte-section { display: flex; flex-direction: column; gap: 6px; padding: 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
.dte-hdr { display: flex; align-items: center; justify-content: space-between; }
.dte-title { font-size: 12px; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: .04em; }
.dte-add-btn { font-size: 11px; padding: 2px 8px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.dte-add-btn:hover { background: #f1f5f9; }
.dte-empty { font-size: 11px; color: #9ca3af; }
</style>
