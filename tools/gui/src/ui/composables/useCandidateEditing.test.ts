/**
 * A candidate sketched on its own picture records what the canvas does: a model element put on it is a
 * reference the candidate reads over, *Remove from view* takes the reference away, and Undo writes the
 * candidate back to what it held. Its picture is read from the candidate, never from a diagram.
 */
import { Effect } from 'effect'
import { describe, expect, it } from 'vitest'
import type { ModelService } from '../../application/ModelService'
import type { Extent } from '../../domain/layout/geometry'
import { SHAPE_DRAWING } from '../../domain/layout/__tests__/canvasDrawingFixtures'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { GeometryComposition } from '../../ports/diagramWriteBodies'
import { useCandidateEditing } from './useCandidateEditing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, key: string, extent: Extent) => ({
  alias, key, label: alias, extent, inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})
const picture = (...elements: ReturnType<typeof element>[]): LayoutGeometry => ({
  artifact_id: '', name: 'Naive', canvas: at(0, 0, 600, 400), backdrop: [],
  surround: { drawn: at(0, 0, 0, 0), parts: [] }, elements, boxes: [], relations: [],
})
const LEDGER = element('L', 'APP@1.ledger', at(20, 40, 120, 80))
const START = { diagram_type: 'archimate-layered', name: 'Naive', entity_ids: [], connection_ids: [] }

/** A server holding one candidate that reads over nothing yet; every write it is sent is kept. */
const fakeServer = () => {
  const calls: string[] = []
  let record: Record<string, unknown> = { id: 'CAND@1.n', scope: [], changes: { operations: [] } }
  let version = 0
  const answer = () => Effect.succeed({ record, version: `v${version}` })
  const svc = {
    readCandidate: () => answer(),
    compareCandidate: () => Effect.succeed({
      candidate: 'CAND@1.n', base: 'model', stack: [], standing: [], diff: [],
      view: { entities: [{ id: 'APP@1.ledger', fields: { name: 'Ledger' } }], connections: [] },
    }),
    readCandidatePicture: () => { calls.push('read picture'); return Effect.succeed(picture()) },
    previewCandidatePicture: (_id: string, composition: { entity_ids: readonly string[] }) => {
      calls.push(`preview ${composition.entity_ids.join(',')}`)
      return Effect.succeed(picture(...composition.entity_ids.includes('APP@1.ledger') ? [LEDGER] : []))
    },
    drawCandidatePictureShapes: () => Effect.succeed([]),
    editCandidate: (_id: string, basedOn: string, patch: Record<string, unknown>) => {
      calls.push(`edit ${basedOn} ${JSON.stringify(patch.scope)}`)
      record = { ...record, ...patch }
      version += 1
      return answer()
    },
    readLayoutGeometry: () => Effect.die('a candidate reads no diagram'),
    previewLayoutGeometry: () => Effect.die('a candidate reads no diagram'),
  } as unknown as ModelService
  return { svc, calls, scope: () => record.scope }
}

const settled = () => new Promise((resolve) => setTimeout(resolve, 30))

describe('useCandidateEditing', () => {
  it('records a model element put on the picture as a reference, and Remove from view takes it away', async () => {
    const server = fakeServer()
    const editing = useCandidateEditing(server.svc, () => START, () => 'CAND@1.n', () => undefined)
    expect(await editing.open()).toBe(true)
    expect(server.calls).toEqual(['read picture'])

    await editing.add('APP@1.ledger', 'Ledger', 'application-component')
    expect(server.scope()).toEqual(['APP@1.ledger'])
    expect(server.calls).toContain('preview APP@1.ledger')

    editing.remove(['L'])
    await settled()
    expect(server.scope()).toEqual([])
  })

  it('composes over what its start states once that picture is read, so the boxes it was read with stay', async () => {
    const server = fakeServer()
    const composed: unknown[] = []
    const svc = {
      ...server.svc,
      previewCandidatePicture: (id: string, composition: GeometryComposition) => {
        composed.push(composition)
        return server.svc.previewCandidatePicture(id, composition)
      },
    } as unknown as ModelService
    const boxes = [{ label: 'Application Components', 'entity-ids': [], rule: { type: 'application-component' } }]
    const starts: (LayoutGeometry | null)[] = []
    const editing = useCandidateEditing(svc, (start) => {
      starts.push(start)
      return start ? { ...START, authored_groupings: boxes } : START
    }, () => 'CAND@1.n', () => undefined)
    await editing.open()
    await editing.add('APP@1.ledger', 'Ledger', 'application-component')

    expect(starts).toContainEqual(picture())
    expect(composed).toEqual([expect.objectContaining({ authored_groupings: boxes })])
  })

  it('writes the references back when Undo takes a step back', async () => {
    const server = fakeServer()
    const editing = useCandidateEditing(server.svc, () => START, () => 'CAND@1.n', () => undefined)
    await editing.open()
    await editing.add('APP@1.ledger', 'Ledger', 'application-component')
    expect(server.scope()).toEqual(['APP@1.ledger'])

    editing.session.undo()
    await settled()
    expect(server.scope()).toEqual([])
  })
})
