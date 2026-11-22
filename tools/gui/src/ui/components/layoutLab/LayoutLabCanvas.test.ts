// @vitest-environment jsdom
/**
 * The lab's canvas draws its pieces in the one paint order, as the pointer leaves them: a box dragged
 * over an element is drawn after it, with the lines into that element drawn just before the box, so
 * the box hides them as it hides the element; and a breach is marked only while breaches are shown,
 * tagged with the rule it breaks.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, reactive } from 'vue'
import type { App } from 'vue'
import type { Extent } from '../../../domain/layout/geometry'
import { drawnArrangement } from '../../../domain/layout/lab/labArrangement'
import { LINE_DRAWING, SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { LabGeometry } from '../../../domain/layout/lab/labGeometry'
import { useLayoutLab } from '../../composables/useLayoutLab'
import LayoutLabCanvas from './LayoutLabCanvas.vue'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** A grouping G holding A, C beside it; a line from A to C. */
const geometry: LabGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], outside_label: null, drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 40, 500, 80), inside: null, words: [], outside_label: null, drawing: SHAPE_DRAWING },
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: null, words: [], title_band: null, drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [400, 60]], label: '', label_size: null, drawing: LINE_DRAWING,
  }],
}

let app: App | null = null

const mounted = async () => {
  const lab = useLayoutLab()
  lab.geometry.value = geometry
  lab.arrangement.value = drawnArrangement(geometry)
  const shown = reactive({ breaches: true })
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(LayoutLabCanvas, { lab, showBreaches: shown.breaches }) })
  app.mount(host)
  await nextTick()
  return { lab, host, shown }
}

/** What is drawn, back to front: a shape by its alias, a line or label by its kind and place. */
const drawnOrder = (host: HTMLElement): string[] =>
  [...host.querySelectorAll('[data-painted]')].map((piece) =>
    piece.getAttribute('data-alias') ?? `${piece.getAttribute('data-painted')}:${piece.getAttribute('data-relation')}`)

const pointer = (target: EventTarget, type: string, x: number, y: number) =>
  target.dispatchEvent(Object.assign(new MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true }), { pointerId: 1 }))

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => { frame(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  // jsdom lays nothing out: the picture is shown at its own scale, so page and picture agree.
  Object.defineProperty(SVGSVGElement.prototype, 'getScreenCTM', {
    configurable: true,
    value: () => ({ inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }) }),
  })
})
afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  Reflect.deleteProperty(SVGSVGElement.prototype, 'getScreenCTM')
})

describe('the layout lab canvas', () => {
  it('draws shapes by nesting, then the lines over them', async () => {
    const { host } = await mounted()
    expect(drawnOrder(host)).toEqual(['G', 'A', 'C', 'line:0'])
  })

  it('draws a box dragged over an element after it, and the element\'s lines under the box', async () => {
    const { host } = await mounted()
    const grip = host.querySelector('[data-alias="G"] > .lab-grip')
    if (grip === null) throw new Error('the grouping is drawn without a grip')
    pointer(grip, 'pointerdown', 15, 15)
    pointer(window, 'pointermove', 400, 15)
    pointer(window, 'pointerup', 400, 15)
    await nextTick()

    expect(drawnOrder(host)).toEqual(['C', 'line:0', 'G', 'A'])
  })

  it('draws the shape being dragged see-through until it is dropped, and nothing else', async () => {
    const { host } = await mounted()
    const grip = host.querySelector('[data-alias="G"] > .lab-grip')
    if (grip === null) throw new Error('the grouping is drawn without a grip')
    pointer(grip, 'pointerdown', 15, 15)
    await nextTick()
    expect(host.querySelectorAll('.lab-carried')).toHaveLength(0)

    pointer(window, 'pointermove', 300, 15)
    await nextTick()
    expect([...host.querySelectorAll('.lab-carried')].map((piece) => piece.getAttribute('data-alias'))).toEqual(['G'])

    pointer(window, 'pointerup', 300, 15)
    await nextTick()
    expect(host.querySelectorAll('.lab-carried')).toHaveLength(0)
  })

  it('marks a breach with the rule it breaks while breaches are shown, and not otherwise', async () => {
    const { lab, host, shown } = await mounted()
    const drawn = drawnArrangement(geometry)
    // C put over A: two connected elements over each other, which no route can satisfy.
    lab.arrangement.value = { ...drawn, elements: new Map([...drawn.elements, ['C', at(60, 50, 160, 90)]]) }
    lab.routeEverything()
    await nextTick()
    expect([...host.querySelectorAll('.lab-breach-tag')].map((tag) => tag.textContent)).toContain('ends overlap')
    // Set off in a box of its own with a leader, never as a stroke laid along the line.
    expect(host.querySelectorAll('.lab-breach-tag-box').length).toBe(host.querySelectorAll('.lab-breach-tag').length)
    expect(host.querySelectorAll('.lab-breach-leader').length).toBe(host.querySelectorAll('.lab-breach-tag').length)

    shown.breaches = false
    await nextTick()
    expect(host.querySelectorAll('.lab-breach-mark')).toHaveLength(0)
  })
})
