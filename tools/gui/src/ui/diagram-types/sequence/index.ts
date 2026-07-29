import { defineComponent } from 'vue'
import { registerExtension } from '../../lib/diagramAuthoringExtensions'
import { registerViewerExtension } from '../../lib/diagramViewerExtensions'
import { sequenceMapElements } from './sequenceElementMapping'
import SequenceEditor from './SequenceEditor.vue'

// Sequence has no node-subpart selection (unlike datatype's classifier attribute rows); this
// extension only contributes `mapElements`, so the panel is never shown.
const NoSubPartDetail = defineComponent({ render: () => null })

export function register(): void {
  registerExtension('sequence-editor', SequenceEditor, {
    managedOwnTypes: ['lifeline', 'message', 'grouping', 'note'],
  })
  registerViewerExtension('sequence', {
    attachNodeSubParts: () => {},
    detailComponent: NoSubPartDetail,
    mapElements: sequenceMapElements,
  })
}
