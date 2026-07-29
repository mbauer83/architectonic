import { registerExtension } from '../../lib/diagramAuthoringExtensions'
import C4DiagramEditor from './C4DiagramEditor.vue'

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
}
