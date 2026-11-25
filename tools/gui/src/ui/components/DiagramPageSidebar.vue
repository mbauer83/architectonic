<script setup lang="ts">
/**
 * The diagram page's panel beside the canvas: the entity list with its find field, the selection's
 * detail, and above them what the mode leads with — the reader's panel in view mode, the picker of
 * what to add in edit mode. Docked over the canvas in fullscreen (`FullscreenDock`).
 *
 * Choosing an element in the list *finds* it in view mode — selects it and moves the window to it
 * (owner, Q21); in edit mode the list only selects, since the canvas's own selection is the shapes.
 */
import type { DiagramContext, DiagramContextEntity, EditableMetadataSpec } from '../../domain'
import type { DiagramEditMode } from '../composables/useDiagramEditMode'
import type { useDiagramPageReader } from '../composables/useDiagramPageReader'
import type { useDiagramSvgSelection } from '../composables/useDiagramSvgSelection'
import DiagramEntitySidebar from './DiagramEntitySidebar.vue'
import DiagramMemberPicker from './DiagramMemberPicker.vue'
import { drawnByEntity, relationsDrawn } from '../../domain/layout/canvasComposition'
import DiagramReaderPanel from './DiagramReaderPanel.vue'
import FullscreenDock from './FullscreenDock.vue'

const props = defineProps<{
  context: DiagramContext | null
  entities: readonly DiagramContextEntity[]
  editableMetadataByType: Record<string, EditableMetadataSpec>
  selection: ReturnType<typeof useDiagramSvgSelection>
  reader: ReturnType<typeof useDiagramPageReader>
  edit: DiagramEditMode
  editing: boolean
  fullscreenHost: HTMLElement | null
  isFullscreen: boolean
}>()

/** The label being typed for the selected line: the selection holds it, this panel edits it. */
const { edgeLabelInput } = props.selection
const editEdgeLabel = (text: string) => { edgeLabelInput.value = text }

const choose = (id: string) => {
  if (props.editing) props.selection.selectEntity(id)
  else props.reader.find(id)
}
</script>

<template>
  <FullscreenDock
    :fullscreen-host="fullscreenHost"
    :is-fullscreen="isFullscreen"
    :revealed="selection.hasSelection.value"
  >
    <DiagramEntitySidebar
      :list-folded="reader.reading.value"
      :entities="entities"
      :viewer-extension="selection.viewerExtension.value"
      :selected-id="selection.selectedId.value"
      :selected-connection="selection.selectedConnection.value"
      :selected-sub-part="selection.selectedSubPart.value"
      :selected-entity-record="selection.selectedEntityRecord.value"
      :editable-metadata-by-type="editableMetadataByType"
      :selection-token="selection.selectionToken.value"
      :entity-query="selection.entityQuery"
      :edge-label-input="selection.edgeLabelInput.value"
      :edge-label-error="selection.edgeLabelMutation.errorMessage.value"
      :metadata-error="selection.metadataMutation.errorMessage.value"
      @select-entity="selection.selectEntity($event)"
      @find="choose"
      @clear-connection="selection.clearConnection()"
      @clear-sub-part="selection.clearSubPart()"
      @update:edge-label-input="editEdgeLabel"
      @save-edge-label="selection.saveEdgeLabel()"
      @sub-part-save="selection.patchEntityMetadata($event)"
      @entity-meta-save="selection.patchEntityMetadata($event)"
      @entity-edited="selection.entityEdited()"
    >
      <template #lead>
        <DiagramMemberPicker
          v-if="editing && context"
          :context="context"
          :busy="edit.editing.loading.value || edit.editing.saving.value"
          :drawn="drawnByEntity(context, edit.session.state.value, edit.session.geometry.value)"
          :drawn-relations="relationsDrawn(context, edit.session.state.value)"
          @add="(entity) => edit.editing.add(entity.artifact_id, entity.name, entity.artifact_type)"
          @draw="(id) => edit.editing.drawRelation(id)"
          @select="edit.select"
          @outline="edit.outline"
          @outward="edit.escape"
        />
        <DiagramReaderPanel
          v-if="reader.reading.value"
          v-bind="reader.panel.value"
          v-on="reader.panelEvents"
        />
      </template>
    </DiagramEntitySidebar>
  </FullscreenDock>
</template>
