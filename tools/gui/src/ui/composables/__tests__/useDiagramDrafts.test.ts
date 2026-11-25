// @vitest-environment jsdom
/**
 * In view mode the rendered picture marks each draft with the same quiet "d" the edit canvas draws, in
 * its drawing's top right corner, once however often the page reads the picture, and hidden from a
 * reader, who hears "draft" from the element's own name instead.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref, shallowRef } from 'vue'
import type { DiagramContext } from '../../../domain'
import type { DiagramEditing } from '../useDiagramEditing'
import { useDiagramDrafts } from '../useDiagramDrafts'

const SVG = 'http://www.w3.org/2000/svg'
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

describe('the draft marker in view mode', () => {
  it('writes one "d" into each draft\'s drawing, top right, and none into the rest', async () => {
    const picture = document.createElementNS(SVG, 'svg')
    document.body.appendChild(picture)
    const drawing = (id: string) => {
      const group = document.createElementNS(SVG, 'g')
      group.setAttribute('id', id)
      picture.appendChild(group)
      return group
    }
    const draft = drawing('draft')
    const done = drawing('done')
    Object.defineProperty(SVGElement.prototype, 'getBBox', {
      configurable: true, value: () => ({ x: 10, y: 20, width: 100, height: 40 }),
    })
    const context = ref({
      entities: [{ artifact_id: 'BOB@1.a.note', status: 'draft' }, { artifact_id: 'BOB@2.b.kept', status: 'active' }],
    } as unknown as DiagramContext)
    const nodeElements = shallowRef<ReadonlyMap<string, readonly Element[]>>(new Map())
    const editing = { session: { state: ref(null), geometry: ref(null) } } as unknown as DiagramEditing
    const scope = effectScope()
    scope.run(() => useDiagramDrafts({ context, editing, nodeElements }))
    nodeElements.value = new Map([['BOB@1.a.note', [draft]], ['BOB@2.b.kept', [done]]])
    await nextTick()
    nodeElements.value = new Map(nodeElements.value)
    await nextTick()
    const marks = [...picture.querySelectorAll('[data-draft-mark]')]
    expect(marks.map((mark) => [mark.parentElement?.id, mark.textContent, mark.getAttribute('x'), mark.getAttribute('y')]))
      .toEqual([['draft', 'd', '106', '33']])
    expect(marks[0]?.getAttribute('aria-hidden')).toBe('true')
    scope.stop()
    Reflect.deleteProperty(SVGElement.prototype, 'getBBox')
  })
})
