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
import type { ModelService } from '../../application/ModelService'
import type { PictureContext } from '../../domain'
import type { CandidateComparison } from '../../domain/schemas/candidates'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { GeometryComposition } from '../../ports/diagramWriteBodies'
import { drawnCommands } from '../../domain/candidates/candidateDrawing'
import { arrangedBy, layoutOf } from '../../domain/layout/arrangementLayout'
import { composeCanvas } from '../../domain/layout/canvasComposition'
import { membershipOf } from '../../domain/layout/diagramMembership'

export type ComposedDrawingAccess = Pick<ModelService,
  'getDiagramContext' | 'previewLayoutGeometry' | 'readCandidatePictureContext' | 'previewCandidatePicture'>

/** Where a composed picture's context is read and its composition previewed. */
interface ComposedPictureSource {
  readonly context: () => Promise<PictureContext>
  readonly preview: (composition: GeometryComposition) => Promise<LayoutGeometry>
}

export function useComposedDrawing(svc: ComposedDrawingAccess, comparison: () => CandidateComparison | null) {
  const drawing = shallowRef<LayoutGeometry | null>(null)
  // A stored diagram's context is the same for every candidate drawn on it; a candidate's own moves with it.
  const contexts = new Map<string, Promise<PictureContext>>()
  const diagramContext = (id: string): Promise<PictureContext> => {
    const known = contexts.get(id) ?? Effect.runPromise(svc.getDiagramContext(id))
    contexts.set(id, known)
    return known
  }

  const sourceOf = (read: CandidateComparison, base: LayoutGeometry | null): ComposedPictureSource => {
    const diagram = base?.artifact_id
    return diagram
      ? {
        context: () => diagramContext(diagram),
        preview: (composition) => Effect.runPromise(svc.previewLayoutGeometry(diagram, composition)),
      }
      : {
        context: () => Effect.runPromise(svc.readCandidatePictureContext(read.candidate)),
        preview: (composition) => Effect.runPromise(svc.previewCandidatePicture(read.candidate, composition)),
      }
  }

  const composed = async (read: CandidateComparison, base: LayoutGeometry | null): Promise<LayoutGeometry | null> => {
    const source = sourceOf(read, base)
    const context = await source.context()
    const membership = membershipOf(context.diagram)
    const commands = drawnCommands(read.view, {
      entities: context.entities, connections: context.connections, undrawn: context.candidate_connections,
    })
    if (!membership || !commands.length) return base
    const { preview } = composeCanvas(membership, { commands }, new Set())
    // A picture arranged by hand stays as arranged; what the candidate adds is placed beside its neighbours.
    const arrangement = base?.layout ? { arrangement: layoutOf(base, arrangedBy(base, base.layout)) } : {}
    return source.preview({ ...preview, ...arrangement })
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
