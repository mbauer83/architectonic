/**
 * The picture a candidate is read on, with the candidate drawn as it composes (`drawnCommands`): what it
 * creates, renames and links drawn by the diagram editor's own composition and preview, so a read canvas
 * shows what the sketching canvas showed. The one composer of that picture for every reader of a candidate —
 * its page, a comparison and the stress workspace.
 *
 * It is composed over the picture its comparison was served with, read where that picture comes from: a
 * stored diagram's own context and preview, or — for a view generated from what the candidate reads over, or
 * no picture at all yet — the candidate's own picture (`candidates.picture`), which starts from exactly that.
 * Where the candidate changes nothing the picture draws, the picture is the one its comparison was served
 * with. A preview the server refuses leaves that picture standing too: the read never fails on it.
 */
import { shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { PictureContext } from '../../domain'
import type { CandidateComparison } from '../../domain/schemas/candidates'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { composedOver, drawnCommands } from '../../domain/candidates/candidateDrawing'
import { arrangedBy, layoutOf } from '../../domain/layout/arrangementLayout'
import { composeCanvas } from '../../domain/layout/canvasComposition'
import { candidatePicture, diagramPicture, type PictureSource } from './pictureSource'

/** What the two picture sources read through (`pictureSource`). */
export type ComposedDrawingAccess = Parameters<typeof diagramPicture>[0] & Parameters<typeof candidatePicture>[0]

export function useComposedDrawing(svc: ComposedDrawingAccess, comparison: () => CandidateComparison | null) {
  const drawing = shallowRef<LayoutGeometry | null>(null)
  // A stored diagram's context is the same for every candidate drawn on it; a candidate's own moves with it.
  const contexts = new Map<string, Promise<PictureContext>>()
  const contextOf = (source: PictureSource, diagram: string | undefined): Promise<PictureContext> => {
    if (!diagram) return Effect.runPromise(source.context())
    const known = contexts.get(diagram) ?? Effect.runPromise(source.context())
    contexts.set(diagram, known)
    return known
  }

  const composed = async (read: CandidateComparison, base: LayoutGeometry | null): Promise<LayoutGeometry | null> => {
    const diagram = base?.artifact_id || undefined
    const source = diagram ? diagramPicture(svc, () => diagram) : candidatePicture(svc, () => read.candidate)
    const context = await contextOf(source, diagram)
    const membership = composedOver(context.diagram, base)
    const commands = drawnCommands(read.view, {
      entities: context.entities, connections: context.connections, undrawn: context.candidate_connections,
    })
    if (!membership || !commands.length) return base
    const { preview } = composeCanvas(membership, { commands }, new Set())
    // A picture arranged by hand stays as arranged; what the candidate adds is placed beside its neighbours.
    const arrangement = base?.layout ? { arrangement: layoutOf(base, arrangedBy(base, base.layout)) } : {}
    return Effect.runPromise(source.preview({ ...preview, ...arrangement }))
  }

  watch(comparison, async (read) => {
    const base = read?.drawing ?? null
    drawing.value = base
    if (!read) return
    const drawn = await composed(read, base).catch(() => base)
    if (comparison() === read) drawing.value = drawn
  }, { immediate: true })

  return drawing
}
