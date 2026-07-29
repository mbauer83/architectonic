import { registerExtension } from '../../lib/diagramAuthoringExtensions'
import { registerViewerExtension } from '../../lib/diagramViewerExtensions'
import AttributeDetailPanel from './AttributeDetailPanel.vue'
import { attachClassifierAttributeRows } from './attributeSelection'
import ClassifierMetadataSection from './ClassifierMetadataSection.vue'
import DatatypeEditor from './DatatypeEditor.vue'

export function register(): void {
  registerExtension('datatype-editor', DatatypeEditor, {
    // Every own type the bespoke editor covers — anything omitted here is ALSO rendered by
    // the generic DiagramOwnEntityTypeSection, producing two competing UIs for one concept.
    managedOwnTypes: ['classifier', 'generalization_set'],
  })
  // Viewer: make classifier attribute rows selectable, with a sidebar detail panel; and a
  // classifier metadata section rendered inside the generic selected-entity panel.
  registerViewerExtension('datatype', {
    attachNodeSubParts: attachClassifierAttributeRows,
    detailComponent: AttributeDetailPanel,
    entityDetailSection: ClassifierMetadataSection,
  })
}
