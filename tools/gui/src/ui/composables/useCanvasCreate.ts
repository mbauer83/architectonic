/**
 * Adding to the diagram at the point its menu was opened (sketch 03·1–3, 03·11): which box the point
 * is in, and what is done with what the menu chose there — a new draft, an element found in the model,
 * or one already drawn drawn again. On a picture arranged by hand the new drawing is placed at the
 * point; where PlantUML arranges the picture it places it, as it places everything else. What was added
 * is selected, so the arrows move it; a draft made inside a container element is then asked whether it
 * becomes a part of it ("Make X part of Y?"), because nesting in an element is that relation.
 */
import { ref, type ComputedRef, type Ref } from 'vue'
import type { PictureContext, EntityDisplayInfo } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import type { Point } from '../../domain/layout/geometry'
import { type ReceivingBox, receivingBoxAt } from '../../domain/layout/receivingBox'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { pointOnPicture } from '../components/canvas/pointerOnPicture'
import type { CanvasPopoverLevel } from './useCanvasPopover'
import type { DiagramEditing } from './useDiagramEditing'

type Member = { readonly alias: string; readonly id: string; readonly name: string; readonly type: string }

export function useCanvasCreate(
  editing: DiagramEditing, host: Ref<HTMLElement | null>, context: () => PictureContext,
  members: ComputedRef<readonly Member[]>,
  popover: {
    readonly mode: Ref<CanvasPopoverLevel | null>
    readonly error: Ref<string>
    readonly close: (refocus?: boolean) => void
    /** The element the nest question is about, and the one it asks to nest it in. */
    readonly source: Ref<string>
    readonly asked: Ref<string | null>
  },
  select: (alias: string) => void,
) {
  const { mode, error, close, source, asked } = popover
  /** The box under the point the menu was opened at; null on open paper. */
  const into = ref<ReceivingBox | null>(null)
  /** That point, on the picture. */
  const clicked = ref<Point | null>(null)

  /** Where the menu opened: the point on the picture, and the innermost box drawn under it. */
  const openedAt = (event: { clientX: number; clientY: number }): ReceivingBox | null => {
    const at = pointOnPicture(host.value?.querySelector('svg') ?? null, event)
    const geometry = editing.session.geometry.value
    const placement = editing.session.placement.value
    const elementOf = (key: string) => members.value.find((one) => stableEntityId(one.id) === stableEntityId(key))
    clicked.value = at
    into.value = geometry && placement
      ? receivingBoxAt(geometry, placement.boxes, at, context().diagram.authored_groupings ?? [], elementOf) : null
    return into.value
  }

  /** The point a new drawing is placed at: the menu's, on a picture arranged by hand; none otherwise. */
  const placeOf = (id: string): readonly [string, Point] | undefined =>
    editing.session.state.value?.byHand && clicked.value ? [id, clicked.value] : undefined
  const aliasOf = (id: string) => editing.session.geometry.value?.elements
    .find((one) => stableEntityId(one.key ?? '') === stableEntityId(id))?.alias
  const failed = () => { error.value = editing.error.value ?? 'The drawing has changed. Try again.' }

  /** The draft *command* creates, placed and selected; inside a container, asked whether it is a part. */
  const created = async (command: CanvasCommand) => {
    if (!await editing.propose(command, undefined, placeOf(command.artifact_id))) return failed()
    const alias = aliasOf(command.artifact_id)
    if (alias) select(alias)
    const box = into.value
    if (alias && box?.admits.kind === 'parts') {
      source.value = alias
      asked.value = box.admits.container
      mode.value = 'nest'
    } else close(true)
  }

  /** An element found in the model, drawn here and selected. */
  const found = async (entity: EntityDisplayInfo) => {
    await editing.add(entity.artifact_id, entity.name, entity.artifact_type, placeOf(entity.artifact_id)?.[1])
    const alias = aliasOf(entity.artifact_id)
    if (alias) select(alias)
    close(true)
  }

  /** An element already drawn, drawn once more where the menu was opened (03·1). */
  const again = async (entity: EntityDisplayInfo) => {
    const own = stableEntityId(entity.artifact_id)
    const drawn = context().entities.find((one) => stableEntityId(one.artifact_id) === own)
    if (!drawn) return
    const added = await editing.addOccurrence(
      { artifact_id: drawn.artifact_id, name: drawn.name, display_alias: drawn.display_alias },
      clicked.value ?? undefined,
    )
    if (added) close(true)
    else failed()
  }

  return { into, openedAt, created, found, again }
}
