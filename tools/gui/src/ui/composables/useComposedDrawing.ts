/**
 * The picture a candidate is read on, with the candidate drawn as it composes (`drawnCommands`): what it
 * creates, renames and links drawn by the diagram editor's own composition and preview, so a read canvas
 * shows what the sketching canvas showed. Where the candidate changes nothing the picture draws, or is
 * drawn on a generated view no stored diagram backs, the picture is the one its comparison was served
 * with. A preview the server refuses leaves that picture standing too: the read never fails on it.
 */
import { shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext } from '../../domain'
import type { CandidateComparison } from '../../domain/schemas/candidates'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { drawnCommands } from '../../domain/candidates/candidateDrawing'
import { arrangedBy, layoutOf } from '../../domain/layout/arrangementLayout'
import { composeCanvas } from '../../domain/layout/canvasComposition'
import { membershipOf } from '../../domain/layout/diagramMembership'

export type ComposedDrawingAccess = Pick<ModelService, 'getDiagramContext' | 'previewLayoutGeometry'>

export function useComposedDrawing(svc: ComposedDrawingAccess, comparison: () => CandidateComparison | null) {
  const drawing = shallowRef<LayoutGeometry | null>(null)
  const contexts = new Map<string, Promise<DiagramContext>>()
  const contextOf = (id: string): Promise<DiagramContext> => {
    const known = contexts.get(id) ?? Effect.runPromise(svc.getDiagramContext(id))
    contexts.set(id, known)
    return known
  }

  const composed = async (read: CandidateComparison, base: LayoutGeometry): Promise<LayoutGeometry> => {
    const context = await contextOf(base.artifact_id)
    const membership = membershipOf(context.diagram)
    const commands = drawnCommands(read.view, {
      entities: context.entities, connections: context.connections, undrawn: context.candidate_connections,
    })
    if (!membership || !commands.length) return base
    const { preview } = composeCanvas(membership, { commands }, new Set())
    // A picture arranged by hand stays as arranged; what the candidate adds is placed beside its neighbours.
    const arrangement = base.layout ? { arrangement: layoutOf(base, arrangedBy(base, base.layout)) } : {}
    return Effect.runPromise(svc.previewLayoutGeometry(base.artifact_id, { ...preview, ...arrangement }))
  }

  watch(comparison, async (read) => {
    const base = read?.drawing ?? null
    drawing.value = base
    if (!read || !base?.artifact_id) return
    const drawn = await composed(read, base).catch(() => base)
    if (comparison() === read) drawing.value = drawn
  }, { immediate: true })

  return drawing
}
