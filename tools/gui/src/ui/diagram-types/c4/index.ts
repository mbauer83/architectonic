import { defineComponent } from 'vue'
import { registerExtension } from '../../lib/diagramAuthoringExtensions'
import { registerViewerExtension } from '../../lib/diagramViewerExtensions'
import { c4MapElements } from './c4ElementMapping'
import C4DiagramEditor from './C4DiagramEditor.vue'

// C4 has no node-subpart selection (unlike datatype's classifier attribute rows); these
// extensions only contribute `mapElements`, so the panel is never shown.
const NoSubPartDetail = defineComponent({ render: () => null })

const C4_VIEWER_TYPES = ['c4-system-context', 'c4-container', 'c4-component'] as const

export function register(): void {
  registerExtension('c4-editor-context', C4DiagramEditor, {
    managedOwnTypes: ['person', 'software-system'],
    config: { scopeEntityType: 'software-system' },
  })
  registerExtension('c4-editor-container', C4DiagramEditor, {
    managedOwnTypes: ['person', 'software-system', 'container'],
    config: { scopeEntityType: 'software-system' },
  })
  registerExtension('c4-editor-component', C4DiagramEditor, {
    managedOwnTypes: ['person', 'software-system', 'container', 'component'],
    config: { scopeEntityType: 'container' },
  })
  for (const diagramType of C4_VIEWER_TYPES) {
    registerViewerExtension(diagramType, {
      attachNodeSubParts: () => {},
      detailComponent: NoSubPartDetail,
      mapElements: c4MapElements,
    })
  }
}
