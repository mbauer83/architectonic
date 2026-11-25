/**
 * An element of the model carried by a drag from a panel onto a canvas (sketch 01·8): written by the row
 * dragged, read by the canvas it is dropped on. One spelling, here, for both ends.
 *
 * The element travels whole — id, name and type — because a search result is not among what the
 * diagram's context read holds, and the canvas has nowhere else to learn its name from.
 */
import { isRecord } from '../../domain/records'

/** The drag's own media type: nothing else is read as an element being carried. */
const ENTITY_DRAG_TYPE = 'application/x-architectonic-entity'

/** The element a drag carries. */
export interface CarriedEntity {
  readonly artifact_id: string
  readonly name: string
  readonly artifact_type?: string
}

/** Put *entity* on the drag *transfer*. */
export const carryEntity = (transfer: DataTransfer | null, entity: CarriedEntity): void => {
  if (!transfer) return
  transfer.setData(ENTITY_DRAG_TYPE, JSON.stringify({
    artifact_id: entity.artifact_id, name: entity.name,
    ...(entity.artifact_type ? { artifact_type: entity.artifact_type } : {}),
  }))
  transfer.effectAllowed = 'copy'
}

/** Whether the drag *transfer* carries an element: readable while it is dragged, before its data is. */
export const carriesEntity = (transfer: DataTransfer | null): boolean =>
  Boolean(transfer?.types.includes(ENTITY_DRAG_TYPE))

const isCarried = (value: unknown): value is CarriedEntity =>
  isRecord(value) && typeof value.artifact_id === 'string' && typeof value.name === 'string'
  && ['string', 'undefined'].includes(typeof value.artifact_type)

/** The element the dropped *transfer* carries; null when it carries none, or something else. */
export const carriedEntity = (transfer: DataTransfer | null): CarriedEntity | null => {
  const text = transfer?.getData(ENTITY_DRAG_TYPE)
  if (!text) return null
  try {
    const value: unknown = JSON.parse(text)
    return isCarried(value) ? value : null
  } catch {
    return null
  }
}
