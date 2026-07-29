import { defineComponent } from 'vue'
import { registerExtension } from '../../lib/diagramAuthoringExtensions'
import { registerViewerExtension } from '../../lib/diagramViewerExtensions'
import { activityMapElements } from './activityElementMapping'
import ActivityStepEditor from './ActivityStepEditor.vue'

// Activity has no node-subpart selection (unlike datatype's classifier attribute rows); this
// extension only contributes `mapElements`, so the panel is never shown.
const NoSubPartDetail = defineComponent({ render: () => null })

export function register(): void {
  registerExtension('activity-steps', ActivityStepEditor, {
    managedOwnTypes: ['action', 'decision', 'fork', 'partition', 'note'],
  })
  registerViewerExtension('activity', {
    attachNodeSubParts: () => {},
    detailComponent: NoSubPartDetail,
    mapElements: activityMapElements,
  })
}
