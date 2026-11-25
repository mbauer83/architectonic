/**
 * Where an element goes on the canvas beyond its position: into or out of one of the diagram's own boxes,
 * into an element by a containment relationship, and drawn once more (03·5, 03·9–11). The popover's
 * level and its error are the caller's (`useCanvasPopover`); this decides what each gesture proposes.
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { connectionId } from '../../domain/artifactId'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { pointOnPicture } from '../components/layoutLab/pointerOnPicture'
import type { CanvasPopoverLevel } from './useCanvasPopover'
import type { DiagramEditing } from './useDiagramEditing'

type Member = { readonly alias: string; readonly id: string; readonly name: string }

export function useCanvasNesting(
  editing: DiagramEditing, host: Ref<HTMLElement | null>, source: Ref<string>,
  members: ComputedRef<readonly Member[]>,
  popover: {
    readonly mode: Ref<CanvasPopoverLevel | null>
    readonly error: Ref<string>
    readonly position: (x: number, y: number) => void
    readonly close: (refocus?: boolean) => void
  },
  apply: (command: CanvasCommand) => void,
) {
  const { mode, error, position, close } = popover
  const failed = () => { error.value = editing.error.value ?? 'The drawing has changed. Try again.' }
  const chosen = computed(() => members.value.find((one) => one.alias === source.value))

  /** Where the menu was opened, on screen: where *Add another occurrence here* puts the drawing. */
  const anchor = ref({ x: 0, y: 0 })
  const drawAgain = async () => {
    const el = chosen.value
    if (!el) return
    const svg = host.value?.querySelector('svg') ?? null
    const at = pointOnPicture(svg, { clientX: anchor.value.x, clientY: anchor.value.y })
    if (await editing.addOccurrence({ artifact_id: el.id, name: el.name, display_alias: source.value }, at)) close(true)
    else failed()
  }

  /** The diagram's own boxes, by alias and label, and the one the chosen element is drawn in. */
  const ownBoxes = computed(() => (editing.session.geometry.value?.boxes ?? [])
    .filter((box) => box.kind === 'authored-grouping').map((box) => ({ alias: box.alias, name: box.label })))
  const boxOfSelected = computed(() => {
    const inside = editing.session.geometry.value?.elements.find((one) => one.alias === source.value)?.inside
    return ownBoxes.value.find((box) => box.alias === inside) ?? null
  })
  const nestIn = async (box: string | null) => {
    if (await editing.nest(source.value, box)) close(true)
    else failed()
  }
  /** Nested in an element: the containment relationship from it, kept as a model change. */
  const nestUnder = (container: string, kind: string) => {
    const whole = members.value.find((one) => one.alias === container)
    const part = chosen.value
    if (!whole || !part) return
    apply({
      op: 'model.relation.create', artifact_id: connectionId(whole.id, kind, part.id),
      description: '', src_multiplicity: '', tgt_multiplicity: '',
    })
  }

  /** The element a drop asked to nest in, which *Nest in…* opens on; null when opened from the menu. */
  const asked = ref<string | null>(null)
  watch(mode, (now) => { if (now !== 'nest') asked.value = null })
  /**
   * An element dropped on a shape (03·9, Q13): onto one of the diagram's own boxes it is nested there,
   * as diagram content; onto an element the question of making it part of that element is asked; onto a
   * box a rule draws, one line says the box draws by its rule. Dropped where it already is, nothing is.
   */
  const dropped = (alias: string, target: string, x: number, y: number) => {
    const geometry = editing.session.geometry.value
    const moved = geometry?.elements.find((one) => one.alias === alias)
    if (!geometry || !moved || moved.inside === target) return
    source.value = alias
    position(x, y)
    const box = geometry.boxes.find((one) => one.alias === target)
    if (box?.kind === 'authored-grouping') void nestIn(target)
    else if (box) {
      mode.value = 'nest'
      error.value = `${box.label} draws what its rule admits; ${moved.label} is not put in it by hand.`
    } else if (geometry.elements.some((one) => one.alias === target)) {
      asked.value = target
      mode.value = 'nest'
    }
  }

  return { anchor, drawAgain, ownBoxes, boxOfSelected, nestIn, nestUnder, asked, dropped }
}
