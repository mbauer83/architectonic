/**
 * A panel row dropped on the canvas (sketch 01·8): the element it carries is added where it lands —
 * placed at the drop point on a picture arranged by hand, laid out by PlantUML on an automatic one
 * (`useDiagramEditing.add`). While a row is dragged over the canvas, the canvas is lit, so it is plain
 * where a drop lands; anything else dragged over it lights nothing.
 */
import { ref, type Ref } from 'vue'
import { carriedEntity, carriesEntity } from '../lib/entityDrag'
import { pointOnPicture } from '../components/canvas/pointerOnPicture'
import type { DiagramEditing } from './useDiagramEditing'

export function useEntityDrop(host: Ref<HTMLElement | null>, editing: DiagramEditing) {
  /** Whether an element is being dragged over the canvas. */
  const lit = ref(false)

  const over = (event: DragEvent) => {
    if (!carriesEntity(event.dataTransfer)) return
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
    lit.value = true
  }
  /** Left for somewhere outside the canvas, not for a shape inside it. */
  const leave = (event: DragEvent) => {
    if (!(event.relatedTarget instanceof Node && host.value?.contains(event.relatedTarget))) lit.value = false
  }
  const drop = (event: DragEvent) => {
    lit.value = false
    const entity = carriedEntity(event.dataTransfer)
    if (!entity) return
    event.preventDefault()
    const at = pointOnPicture(host.value?.querySelector('svg') ?? null, event)
    void editing.add(entity.artifact_id, entity.name, entity.artifact_type, at)
  }

  return { lit, over, leave, drop }
}
