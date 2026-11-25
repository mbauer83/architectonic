/**
 * What Save would write is read off the state, never counted: a move adds a change and its undo takes
 * it away, returning to automatic leaves no arranging change, and a save is the new starting point.
 */
import { Effect } from 'effect'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ModelService } from '../../application/ModelService'
import type { Extent } from '../../domain/layout/geometry'
import { moved } from '../../domain/layout/lab/labArrangement'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { LayoutPatch } from '../../ports/DiagramLayoutRepository'
import type { DiagramReplaceBody } from '../../ports/diagramWriteBodies'
import { useDiagramEditing } from './useDiagramEditing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, key: string, extent: Extent) => ({
  alias, key, label: alias, extent, inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})

const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [element('A', 'APP@1.a', at(20, 40, 120, 80)), element('C', 'APP@3.c', at(400, 40, 500, 80))],
  boxes: [],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

const sent: LayoutPatch[] = []
const written: DiagramReplaceBody[] = []
const MEMBERSHIP = {
  diagram_type: 'archimate-layered', name: 'Test', entity_ids: ['APP@1.a', 'APP@3.c'],
  connection_ids: ['APP@1.a---APP@3.c@@archimate-serving'],
}
const service = {
  readLayoutGeometry: () => Effect.succeed(geometry),
  drawResizedShapes: () => Effect.succeed([]),
  editDiagram: (_id: string, body: DiagramReplaceBody) => {
    written.push(body)
    return Effect.succeed({ wrote: true, warnings: [] })
  },
  patchLayout: (_id: string, patch: LayoutPatch) => {
    sent.push(patch)
    return Effect.succeed({ artifact_id: 'ARC@1.a.test', wrote: true, warnings: [], errors: [], layout: {
      elements: { 'APP@1.a': { x: 20, y: 40 }, 'APP@3.c': { x: 430, y: 40 } },
    } })
  },
} as unknown as ModelService

const opened = async () => {
  const editing = useDiagramEditing(service, () => 'ARC@1.a.test', () => MEMBERSHIP)
  await editing.open()
  return editing
}

/** Move *alias* by (dx, dy) as one step, the way a drag begins and ends. */
const move = (editing: Awaited<ReturnType<typeof opened>>, alias: string, dx: number) => {
  const { session } = editing
  session.begin()
  const from = session.arrangement.value
  if (from) session.preview(moved(geometry, from, alias, dx, 0), new Set([alias]))
  session.commit()
}

beforeEach(() => {
  sent.length = 0
  written.length = 0
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})

describe('the changes a session would save', () => {
  it('starts with none, and a first move counts the element moved, not the takeover as a change of its own',
    async () => {
      const editing = await opened()
      expect(editing.changes.value).toEqual([])
      move(editing, 'C', 30)
      expect(editing.changes.value.map((change) => change.key)).toEqual(['C'])
    })

  it('counts a line shaped by hand as a change of its own, even as the first step', async () => {
    const editing = await opened()
    editing.session.change((_drawn, now) => ({ ...now, routes: new Map(now.routes).set('r', { via: [[260, 120]] }) }))
    expect(editing.changes.value).toEqual([{ key: 'line:0', text: 'Arranged: the line A → C' }])
    expect(editing.undoStep.value).toBe('Arranged: the line A → C')
  })

  it('follows undo and redo, and returning to automatic leaves nothing to save', async () => {
    const editing = await opened()
    move(editing, 'C', 30)
    editing.session.undo()
    expect(editing.changes.value).toEqual([])
    editing.session.redo()
    expect(editing.changes.value).toHaveLength(1)
    editing.returnToAutomatic()
    expect(editing.changes.value).toEqual([])
  })

  it('saves the arrangement as a patch read against nothing stored, and starts again from it', async () => {
    const editing = await opened()
    move(editing, 'C', 30)
    expect(await editing.save()).toBe(true)
    expect(sent).toHaveLength(1)
    expect(sent[0].elements['APP@3.c']).toEqual({ value: { x: 430, y: 40 }, based_on: null })
    expect(editing.changes.value).toEqual([])
  })

  it('discards back to the last save', async () => {
    const editing = await opened()
    move(editing, 'C', 30)
    editing.discard()
    expect(editing.changes.value).toEqual([])
    expect(editing.session.state.value?.byHand).toBe(false)
  })
})

describe('the step Undo and Redo would take', () => {
  it('is named by what it arranged, and nothing is named where there is no step', async () => {
    const editing = await opened()
    expect(editing.undoStep.value).toBeNull()
    move(editing, 'C', 30)
    expect(editing.undoStep.value).toBe('Arranged: C')
    editing.session.undo()
    expect(editing.undoStep.value).toBeNull()
    expect(editing.redoStep.value).toBe('Arranged: C')
  })

  it('names returning to automatic, and a removal says the element stays in the model', async () => {
    const editing = await opened()
    move(editing, 'C', 30)
    editing.returnToAutomatic()
    expect(editing.undoStep.value).toBe('Return to automatic layout')
    editing.remove(['A'])
    expect(editing.undoStep.value).toBe('Removed from the diagram: A — it stays in the model')
  })
})

describe('removing an element from the diagram', () => {
  it('draws it no more, with its lines, and undo brings both back', async () => {
    const editing = await opened()
    editing.remove(['C'])
    expect(editing.session.geometry.value?.elements.map((one) => one.alias)).toEqual(['A'])
    expect(editing.session.geometry.value?.relations).toEqual([])
    expect(editing.changes.value.map((change) => change.key)).toEqual(['removed:C'])
    editing.session.undo()
    expect(editing.session.geometry.value?.relations).toHaveLength(1)
    expect(editing.changes.value).toEqual([])
  })

  it('removes a selection as one step, passing over a box', async () => {
    const editing = await opened()
    editing.remove(['A', 'C', 'no-such-box'])
    expect(editing.session.geometry.value?.elements).toEqual([])
    expect(editing.session.history.value).toHaveLength(1)
    editing.session.undo()
    expect(editing.session.geometry.value?.elements.map((one) => one.alias)).toEqual(['A', 'C'])
  })

  it('saves the diagram without it and its connections, and leaves the model alone', async () => {
    const editing = await opened()
    editing.remove(['C'])
    expect(await editing.save()).toBe(true)
    expect(written).toHaveLength(1)
    expect(written[0]).toMatchObject({ entity_ids: ['APP@1.a'], connection_ids: [], dry_run: false })
    // One write: the layout travels with the membership, never as a second request after it.
    expect(written[0].layout_patch).toBeDefined()
    expect(sent).toHaveLength(0)
  })
})
