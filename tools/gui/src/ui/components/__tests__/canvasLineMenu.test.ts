// @vitest-environment jsdom
/**
 * A selected line's menu (02·9, Q35): it opens on a right press over a line, or from the menu key or
 * Shift+F10 at the line's middle; Straighten drops the hand bends and keeps the ports, Move end to side
 * puts an end on the side chosen — each one step undo takes back.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import type { App } from 'vue'
import { Effect } from 'effect'
import type { Extent } from '../../../domain/layout/geometry'
import { withRouteStated } from '../../../domain/layout/lab/labRouteEdits'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { useArrangementSession } from '../../composables/useArrangementSession'
import type { DiagramEditing } from '../../composables/useDiagramEditing'
import CanvasLineMenu from '../CanvasLineMenu.vue'
import { asksForTheMenu, isOnALine, selectedLineMiddle } from '../lineMenuPlace'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, extent: Extent) => ({
  alias, key: `APP@1.${alias}`, label: alias, extent, inside: undefined, words: [], outside_label: undefined,
  drawing: SHAPE_DRAWING,
})
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 700, 500), backdrop: [],
  surround: [],
  elements: [element('A', at(20, 40, 120, 80)), element('C', at(400, 240, 500, 280))],
  boxes: [],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [400, 260]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

let app: App | null = null
beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
})
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const mounted = async () => {
  const session = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
  session.open(geometry)
  session.change((_drawn, now) => withRouteStated(now, 'r', {
    from: { side: 'right', at: 0.5 }, to: { side: 'left', at: 0.5 }, via: [[300, 60], [300, 260]],
  }))
  const done = vi.fn()
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(CanvasLineMenu, { editing: { session } as unknown as DiagramEditing, line: 0, onDone: done }) })
  app.mount(host)
  await nextTick()
  return { session, host, done }
}

const item = (host: HTMLElement, name: string) =>
  [...host.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')].find((one) => one.textContent?.trim().startsWith(name))

describe('a line\'s menu', () => {
  it('straightens a line, keeping its ports, as one step', async () => {
    const { session, host, done } = await mounted()
    item(host, 'Straighten')?.click()
    expect(session.arrangement.value?.routes.get('r')).toEqual({ from: { side: 'right', at: 0.5 }, to: { side: 'left', at: 0.5 } })
    expect(done).toHaveBeenCalled()
    session.undo()
    expect(session.arrangement.value?.routes.get('r')?.via).toHaveLength(2)
  })

  it('moves an end onto the side chosen, saying which side it is on now', async () => {
    const { session, host } = await mounted()
    item(host, 'Move end to side')?.click()
    await nextTick()
    expect(host.querySelector('[data-end="to"][aria-current="true"]')?.getAttribute('data-side')).toBe('left')
    host.querySelector<HTMLButtonElement>('[data-end="to"][data-side="top"]')?.click()
    expect(session.arrangement.value?.routes.get('r')).toEqual({ from: { side: 'right', at: 0.5 }, to: { side: 'top', at: 0.5 } })
  })
})

describe('where the menu opens', () => {
  it('on a line, its handles or its label, and from the menu key or Shift+F10', () => {
    const line = document.createElement('div')
    line.className = 'lab-line'
    const inner = document.createElement('span')
    line.appendChild(inner)
    expect(isOnALine(inner)).toBe(true)
    expect(isOnALine(document.body)).toBe(false)
    expect(asksForTheMenu(new KeyboardEvent('keydown', { key: 'ContextMenu' }))).toBe(true)
    expect(asksForTheMenu(new KeyboardEvent('keydown', { key: 'F10', shiftKey: true }))).toBe(true)
    expect(asksForTheMenu(new KeyboardEvent('keydown', { key: 'F10' }))).toBe(false)
    expect(selectedLineMiddle(document.body)).toBeNull()
  })
})
