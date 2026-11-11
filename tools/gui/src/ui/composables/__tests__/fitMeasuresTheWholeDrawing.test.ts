// @vitest-environment jsdom
//
// A diagram is fitted by the extent of everything it draws (B89).
//
// The fit measured the SVG's *first* `<g>`. PlantUML wraps the whole drawing in one, so that was the
// drawing; GSN draws its own SVG, whose first group is one horizontal connector — a box with no
// height — and the fit gave up, leaving a 1451×941 argument unfitted in an 820×658 viewport.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, ref } from 'vue'
import { useFittedPanZoom } from '../useFittedPanZoom'

/** GSN's shape: defs, then a first group holding one horizontal line, then the nodes. */
const GSN_LIKE = `<svg xmlns="http://www.w3.org/2000/svg" width="1451" height="941" viewBox="0 0 1451 941">
  <defs><marker id="m"><path d="M0,0 L0,8 L11,4 z"/></marker></defs>
  <g class="link"><line x1="698" y1="80" x2="1095" y2="80"/></g>
  <g class="node"><rect x="0" y="0" width="1451" height="941"/></g>
</svg>`

const boxes = new Map<string, DOMRect>([
  ['g', { x: 698, y: 80, width: 397, height: 0 } as DOMRect], // the first group: a line
  ['svg', { x: 0, y: 0, width: 1451, height: 941 } as DOMRect], // everything drawn
])

afterEach(() => { vi.restoreAllMocks() })

describe('fitting a diagram whose first group is not the whole drawing', () => {
  it('scales it into the viewport', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      configurable: true,
      value(this: SVGElement) { return boxes.get(this.tagName.toLowerCase()) ?? boxes.get('svg') },
    })
    const container = document.createElement('div')
    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue({ width: 820, height: 658 } as DOMRect)
    const wrapper = document.createElement('div')
    wrapper.innerHTML = GSN_LIKE

    let api!: ReturnType<typeof useFittedPanZoom>
    createApp(defineComponent({
      setup() {
        api = useFittedPanZoom(ref(container), ref(wrapper))
        return () => null
      },
    })).mount(document.createElement('div'))

    await api.fitDiagramToViewport()

    expect(api.scale.value).toBeLessThan(1)
    expect(Number.parseFloat(wrapper.querySelector('svg')!.getAttribute('width')!)).toBeLessThanOrEqual(820)
  })
})
