/**
 * A candidate read on a view generated from its scope draws what it creates: the generated view has no stored
 * diagram behind it, so it is composed over the candidate's own picture, which starts from that view.
 */
import { Effect } from 'effect'
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../domain/layout/geometry'
import { SHAPE_DRAWING } from '../../domain/layout/__tests__/canvasDrawingFixtures'
import type { CandidateComparison } from '../../domain/schemas/candidates'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import { type ComposedDrawingAccess, useComposedDrawing } from './useComposedDrawing'

const STORE = 'APP@1786967678.R_K3YAQ'
const CACHE = 'APP@1795700000.IdxCach.index-read-cache'
const CANDIDATE = 'CAND@1795685981.VJ9xSMc.cached-index-store'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, key: string) => ({
  alias, key, label: alias, extent: at(20, 40, 120, 80), inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})
const picture = (...elements: ReturnType<typeof element>[]): LayoutGeometry => ({
  artifact_id: '', name: 'Cached index store', canvas: at(0, 0, 600, 400), backdrop: [],
  surround: { drawn: at(0, 0, 0, 0), parts: [] }, elements, boxes: [], relations: [],
})
const GENERATED = picture(element('S', STORE))

/** The candidate that creates Index Read Cache and renames the store, read on the view generated from its scope. */
const comparison = (drawing: LayoutGeometry | undefined): CandidateComparison => ({
  candidate: CANDIDATE, base: 'model', stack: [CANDIDATE], standing: [],
  diff: [{ kind: 'entity', target: '$ref:1795700000-IdxCach', change: 'added', fields: {} }],
  view: {
    entities: [
      {
        id: '$ref:1795700000-IdxCach', artifact_id: CACHE,
        fields: { artifact_type: 'application-component', name: 'Index Read Cache', group: 'platform-core' },
      },
      { id: STORE, fields: { artifact_type: 'application-component', name: 'Artifact Index Backing Store' } },
    ],
    connections: [],
  },
  ...(drawing ? { drawing } : {}),
})

const START = {
  diagram: {
    artifact_id: '', name: 'Cached index store', diagram_type: 'archimate-layered',
    entity_ids_used: [STORE], connection_ids_used: [],
  },
  entities: [{ artifact_id: STORE, name: 'Artifact Index Store' }],
  connections: [],
  candidate_connections: [],
}

/** A server that serves the candidate's own picture, and refuses every stored-diagram read. */
const fakeServer = () => {
  const previews: { id: string; composition: unknown }[] = []
  const svc = {
    getDiagramContext: () => Effect.die('a generated view has no stored diagram'),
    previewLayoutGeometry: () => Effect.die('a generated view has no stored diagram'),
    readCandidatePictureContext: () => Effect.succeed(START),
    previewCandidatePicture: (id: string, composition: unknown) => {
      previews.push({ id, composition })
      return Effect.succeed(picture(element('S', STORE), element('C', CACHE)))
    },
  } as unknown as ComposedDrawingAccess
  return { svc, previews }
}

const settled = () => new Promise((resolve) => setTimeout(resolve, 30))

describe('useComposedDrawing', () => {
  it('draws what a candidate creates over the view generated from its scope', async () => {
    const server = fakeServer()
    const read = comparison(GENERATED)
    const drawing = useComposedDrawing(server.svc, () => read)
    await settled()
    expect(server.previews.map((one) => one.id)).toEqual([CANDIDATE])
    expect(JSON.stringify(server.previews[0]?.composition)).toContain(CACHE)
    expect(drawing.value?.elements.map((one) => one.key)).toEqual([STORE, CACHE])
  })

  it('draws what a candidate creates where it reads over nothing the model holds yet', async () => {
    const server = fakeServer()
    const read = comparison(undefined)
    const drawing = useComposedDrawing(server.svc, () => read)
    await settled()
    expect(server.previews.map((one) => one.id)).toEqual([CANDIDATE])
    expect(drawing.value?.elements.map((one) => one.key)).toContain(CACHE)
  })

  it('leaves the served picture standing where the preview is refused', async () => {
    const server = fakeServer()
    const refusing = {
      ...server.svc, previewCandidatePicture: () => Effect.fail({ _tag: 'RepoError', message: 'no' }),
    } as unknown as ComposedDrawingAccess
    const read = comparison(GENERATED)
    const drawing = useComposedDrawing(refusing, () => read)
    await settled()
    expect(drawing.value).toBe(GENERATED)
  })
})
