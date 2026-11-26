/**
 * Where an element goes on the canvas beyond its position: into or out of one of the diagram's own boxes,
 * into an element by a containment relationship, and drawn once more (03·5, 03·9–11). The popover's
 * level and its error are the caller's (`useCanvasPopover`); this decides what each gesture proposes.
 */
import { computed, ref, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import { connectionId } from '../../domain/artifactId'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { pointOnPicture } from '../components/canvas/pointerOnPicture'
import type { CanvasPopoverLevel } from './useCanvasPopover'
import type { DiagramEditing } from './useDiagramEditing'
import type { ArrangementState } from './useArrangementSession'
import type { DropVerdict } from '../../domain/layout/dropVerdict'

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
  apply: (command: CanvasCommand) => Promise<boolean>,
  feedback: {
    /** What a drop on a shape does, once every answer it waits on has come (`useDropFeedback`). */
    readonly settled: (alias: string, target: string) => Promise<DropVerdict | null>
    /** One line said in passing: why a drop was refused, or that a nesting is a pending change. */
    readonly say: (line: string) => void
    readonly nested: (part: string, whole: string) => string
  },
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
  const nestUnder = async (container: string, kind: string) => {
    const whole = members.value.find((one) => one.alias === container)
    const part = chosen.value
    if (!whole || !part) return
    const kept = await apply({
      op: 'model.relation.create', artifact_id: connectionId(whole.id, kind, part.id),
      description: '', src_multiplicity: '', tgt_multiplicity: '',
    })
    // A model change is never silent (03·10): said in passing, while the count beside Save pulses.
    if (kept) feedback.say(feedback.nested(part.name, whole.name))
  }

  /** The element a drop asked to nest in, which *Nest in…* opens on; null when opened from the menu. */
  const asked = ref<string | null>(null)
  /** The session as it stood before the drop that asked: what *Don't nest* returns to. */
  const beforeDrop = shallowRef<ArrangementState | null>(null)
  watch(mode, (now) => {
    if (now === 'nest') return
    asked.value = null
    beforeDrop.value = null
  })
  /**
   * *Don't nest* (03·10): after a drop, the element goes back to where the drag started, as one step
   * that Undo takes back, leaving nothing changed in the session; from the menu, the question closes.
   */
  const dontNest = () => {
    const before = beforeDrop.value
    if (before) editing.session.step(before)
    close(true)
  }
  /**
   * An element dropped on a shape (03·9, Q13): into a box that takes it, as diagram content; onto an
   * element that may hold it, the question of making it part of that element is asked; onto a box or an
   * element that refuses it, one line says why, and it stays where it was dropped. Dropped where it
   * already is, or on a box that draws it by its rule anyway, nothing is said.
   */
  const dropped = async (alias: string, target: string, x: number, y: number) => {
    // The drop is the session's last step: the state before it is where the element came from.
    const [before, now] = [editing.session.history.value.at(-1), editing.session.state.value]
    const said = await feedback.settled(alias, target)
    if (said?.kind === 'refused') return feedback.say(said.why)
    // Acted on only while the element is still where it was dropped: an undo meanwhile asks nothing.
    const where = editing.session.state.value?.arrangement.elements.get(alias)
    if (!said || where !== now?.arrangement.elements.get(alias)) return
    source.value = alias
    position(x, y)
    if (said.kind === 'into') return void nestIn(target)
    beforeDrop.value = before && now && before.arrangement.elements.get(alias) !== now.arrangement.elements.get(alias)
      ? before : null
    asked.value = target
    mode.value = 'nest'
  }

  return { anchor, drawAgain, ownBoxes, boxOfSelected, nestIn, nestUnder, asked, dropped, dontNest }
}
