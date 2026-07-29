<script setup lang="ts">
import { computed } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo, DiagramConnection } from '../../domain'
import { lookupExtension, lookupExtensionConfig, lookupExtensionManagedOwnTypes } from '../lib/diagramAuthoringExtensions'
import DiagramOwnEntityTypeSection from './DiagramOwnEntityTypeSection.vue'

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig | null
  diagramEntities: Record<string, unknown>
  entities?: EntityDisplayInfo[]
  diagramConnections?: DiagramConnection[]
  diagramId?: string
}>()
const emit = defineEmits<{
  diagramEntitiesChange: [patch: Record<string, unknown>]
  diagramConnectionsChange: [connections: DiagramConnection[]]
}>()

const slots = computed(() => Object.entries(props.uiConfig?.type_ui_slots ?? {})
  .map(([slotName, componentKey]) => ({
    slotName,
    componentKey,
    component: lookupExtension(componentKey),
    managedOwnTypes: lookupExtensionManagedOwnTypes(componentKey),
    config: lookupExtensionConfig(componentKey),
  }))
  .filter((slot) => slot.component))

const ownTypes = computed(() => {
  const types = props.uiConfig?.diagram_only_types ?? []
  const managed = new Set(slots.value.flatMap((slot) => slot.managedOwnTypes))
  if (!managed.size) return types
  return types.filter((ownType) => !managed.has(ownType.entity_type))
})
</script>

<template>
  <section
    v-if="uiConfig && (uiConfig.diagram_only_types.length || slots.length)"
    class="kind-panel"
  >
    <DiagramOwnEntityTypeSection
      v-for="ownType in ownTypes"
      :key="ownType.entity_type"
      :config="ownType"
      :diagram-entities="diagramEntities"
      @diagram-entities-change="emit('diagramEntitiesChange', $event)"
    />
    <component
      :is="slot.component"
      v-for="slot in slots"
      :key="slot.slotName"
      :ui-config="uiConfig"
      :diagram-entities="diagramEntities"
      :entities="entities ?? []"
      :diagram-connections="diagramConnections ?? []"
      :diagram-id="diagramId"
      v-bind="slot.config"
      @diagram-entities-change="emit('diagramEntitiesChange', $event)"
      @diagram-connections-change="emit('diagramConnectionsChange', $event)"
    />
  </section>
</template>

<style scoped>
.kind-panel { display: grid; gap: 14px; padding: 10px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }
</style>
