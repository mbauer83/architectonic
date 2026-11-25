/**
 * What an element being moved would land in (sketch 03·9, D7, Q13): while it is dragged, the box or
 * element that would take it is lit with words ("Into Business", "Nest in …"); one that would not stays
 * dark; on release over one that refuses, one line says why (`dropVerdict`).
 *
 * What a box admits is read where the create menu reads it (`admissionOf`); whether an element may hold
 * another is the ontology's answer (`containmentKinds`), asked once per pair of types and kept.
 */
import { ref, shallowRef, type ComputedRef, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { PictureContext } from '../../domain'
import { type DropTarget, type DropVerdict, dropVerdict } from '../../domain/layout/dropVerdict'
import type { Extent } from '../../domain/layout/geometry'
import { admissionOf } from '../../domain/layout/receivingBox'
import { containmentKinds } from '../components/canvasParts'
import { typeWords } from '../components/canvasTypeList'
import type { DiagramEditing } from './useDiagramEditing'

type Member = { readonly alias: string; readonly name: string; readonly type: string }

/** The shape lit as taking what is dragged over it, on screen, and the words it is lit with. */
export interface LitTarget {
  readonly words: string
  readonly at: Extent
}

export function useDropFeedback(
  svc: ModelService, editing: DiagramEditing, host: Ref<HTMLElement | null>, context: () => PictureContext,
  members: ComputedRef<readonly Member[]>,
) {
  /** The layer each element type belongs to, for the diagram type: what a ruled box admits by. */
  const domains = shallowRef<ReadonlyMap<string, string>>(new Map())
  let typesOf: string | null = null
  let typesRead: Promise<unknown> = Promise.resolve()
  const readTypes = () => {
    const diagramType = context().diagram.diagram_type
    if (typesOf === diagramType) return
    typesOf = diagramType
    typesRead = Effect.runPromise(svc.listDiagramElementTypes(diagramType)).then((rows) => {
      domains.value = new Map(rows.map((row) => [String(row.artifact_type), String(row.domain)]))
    }, () => { typesOf = null })
  }

  /** The containment relationships permitted between two types, by "container part"; asked once. */
  const holds = shallowRef<ReadonlyMap<string, readonly string[]>>(new Map())
  const asked = new Map<string, Promise<unknown>>()
  const holdsOf = (container: string, part: string): readonly string[] | undefined => {
    const key = `${container} ${part}`
    if (!asked.has(key)) {
      const keep = (kinds: readonly string[]) => { holds.value = new Map(holds.value).set(key, kinds) }
      asked.set(key, containmentKinds(svc, container, part).then(keep, () => keep([])))
    }
    return holds.value.get(key)
  }

  const memberOf = (alias: string) => members.value.find((one) => one.alias === alias)

  /** The shape *target* as a place to drop *alias* in; null where dropping there changes nothing. */
  const targetOf = (alias: string, target: string): DropTarget | null => {
    const geometry = editing.session.geometry.value
    const moved = geometry?.elements.find((one) => one.alias === alias)
    if (!geometry || !moved || moved.inside === target) return null
    const box = geometry.boxes.find((one) => one.alias === target)
    if (box && box.kind !== 'element') {
      const admits = admissionOf(box, context().diagram.authored_groupings ?? [], undefined)
      return { kind: 'box', name: box.label, ruled: box.kind !== 'authored-grouping', admits }
    }
    const [whole, part] = [memberOf(target), memberOf(alias)]
    if (!whole?.type || !part?.type) return null
    return { kind: 'element', name: whole.name, type: whole.type, holds: holdsOf(whole.type, part.type) }
  }

  /** What dropping *alias* on *target* does, in words; null where there is nothing to say. */
  const verdict = (alias: string, target: string): DropVerdict | null => {
    readTypes()
    const [to, part] = [targetOf(alias, target), memberOf(alias)]
    return to && part
      ? dropVerdict({ name: part.name, type: part.type, domain: domains.value.get(part.type) }, to, typeWords)
      : null
  }

  /** The verdict at a drop, once every answer it waits on has come. */
  const settled = async (alias: string, target: string): Promise<DropVerdict | null> => {
    verdict(alias, target)
    await Promise.all([typesRead, ...asked.values()])
    return verdict(alias, target)
  }

  const lit = ref<LitTarget | null>(null)
  /** *alias* is dragged over *target*, over nothing, or let go (null): light what would take it. */
  const over = (alias: string | null, target?: string) => {
    const said = alias && target ? verdict(alias, target) : null
    const shape = said && said.kind !== 'refused' && target
      ? host.value?.querySelector(`[data-alias="${CSS.escape(target)}"]`) : null
    const rect = shape?.getBoundingClientRect()
    lit.value = said && said.kind !== 'refused' && rect
      ? { words: said.words, at: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom } } : null
  }

  return { lit, over, settled }
}
