// @vitest-environment jsdom
/**
 * The diagram canvas draws its pieces in the one paint order, as the pointer leaves them: a box dragged
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
import type { LayoutGeometry } from '../../../domain/schemas/diagramLayoutGeometry'
import { Effect } from 'effect'
import { useArrangementSession } from '../../composables/useArrangementSession'
import LayoutLabCanvas from './LayoutLabCanvas.vue'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

/** A grouping G holding A, C beside it; a line from A to C. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 600, 400), backdrop: [],
  elements: [
    { alias: 'A', key: 'APP@1.a', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'C', key: 'APP@3.c', label: 'C', extent: at(400, 40, 500, 80), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: undefined, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'A', target: 'C', decorated: [false, true],
    course: [[120, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

let app: App | null = null

const mounted = async () => {
  const lab = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
  lab.open(geometry)
  const shown = reactive({ breaches: true })
  const host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(LayoutLabCanvas, { session: lab, showBreaches: shown.breaches }) })
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

describe('the diagram canvas', () => {
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

  it('marks a breach quietly while breaches are shown, naming it on hover, and not otherwise', async () => {
    const { lab, host, shown } = await mounted()
    const drawn = drawnArrangement(geometry)
    // C put over A: two connected elements over each other, which no route can satisfy.
    lab.state.value = { byHand: true, arrangement: { ...drawn, elements: new Map([...drawn.elements, ['C', at(60, 50, 160, 90)]]) } }
    lab.routeEverything()
    await nextTick()
    const overlap = host.querySelector('.lab-breach-mark[data-rule="ends-overlap"]')
    expect(overlap?.querySelector('title')?.textContent).toBe('A → C joins two elements drawn over each other')
    // Both ends outlined, and no word set on the picture: what is broken is said on hover only.
    expect(overlap?.querySelectorAll('.lab-breach-frame')).toHaveLength(2)
    expect(host.querySelectorAll('.lab-breaches text')).toHaveLength(0)

    shown.breaches = false
    await nextTick()
    expect(host.querySelectorAll('.lab-breach-mark')).toHaveLength(0)
  })

  it('read only, picks what is pressed, moves nothing, and draws what it holds over the picture', async () => {
    const lab = useArrangementSession(() => Effect.succeed([]), (_drawn, automatic) => automatic)
    lab.open(geometry)
    const picked: string[] = []
    const host = document.createElement('div')
    document.body.appendChild(host)
    app = createApp({
      render: () => h(LayoutLabCanvas, { session: lab, readonly: true, onPick: (alias: string) => picked.push(alias) },
        { default: () => h('rect', { class: 'overlay' }) }),
    })
    app.mount(host)
    await nextTick()
    const grip = host.querySelector('[data-alias="A"] > .lab-grip')
    if (grip === null) throw new Error('the element is drawn without a grip')
    const before = lab.arrangement.value
    pointer(grip, 'pointerdown', 30, 50)
    pointer(window, 'pointermove', 300, 200)
    pointer(window, 'pointerup', 300, 200)
    await nextTick()

    expect(picked).toEqual(['A'])
    expect(lab.arrangement.value).toBe(before)
    expect(lab.history.value).toHaveLength(0)
    expect(host.querySelectorAll('.lab-handles')).toHaveLength(0)
    expect(host.querySelector('svg .overlay')).not.toBeNull()
  })

  it('selects a line on a press of its band, shows its handles, and lets go of it on paper', async () => {
    const { lab, host } = await mounted()
    lab.change((_drawn, now) => now)
    await nextTick()
    const band = host.querySelector('.lab-line-hit')
    if (band === null) throw new Error('the line is drawn without a band to press')
    pointer(band, 'pointerdown', 200, 60)
    await nextTick()
    expect(host.querySelector('[data-selected-line="0"]')).not.toBeNull()
    expect(host.querySelectorAll('.lab-line-handles__end')).toHaveLength(2)
    const end = host.querySelector('.lab-line-handles__end[data-end="to"]')
    if (end === null) throw new Error('no end handle')
    pointer(end, 'pointerdown', 400, 60)
    pointer(window, 'pointermove', 420, 30)
    pointer(window, 'pointerup', 420, 30)
    await nextTick()
    expect(lab.arrangement.value?.routes.get('r')?.to?.side).toBe('top')
    pointer(host.querySelector('svg') as Element, 'pointerdown', 590, 390)
    await nextTick()
    expect(host.querySelector('[data-selected-line]')).toBeNull()
  })
})
