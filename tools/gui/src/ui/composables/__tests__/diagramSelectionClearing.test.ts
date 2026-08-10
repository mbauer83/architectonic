// @vitest-environment jsdom
//
// What deselects a diagram entity, and what does not.
//
// Clicking a shape twice used to clear the selection. A reader clicks the same shape twice while
// *reading* it — to bring the panel back into focus, or because the first click landed on a label
// rather than the body — so answering that by taking the panel away is a surprise. Deselection is now
// a click that lands on nothing selectable.
//
// These cover the two selection *rules*. That a background click in a real diagram reaches
// `clearSelection` is asserted in the browser suite instead: the listener only fires on elements the
// renderer's own mapping claims, so a hand-built SVG here would be testing a fixture's resemblance to
// a renderer rather than the behaviour.

import { describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, nextTick, ref } from 'vue'
import { Effect } from 'effect'
import { useDiagramSvgSelection, type DiagramSvgSelectionDetail } from '../useDiagramSvgSelection'
import type { DiagramConnection, DiagramContextEntity } from '../../../domain'

const ENTITY_ID = 'ACT@1000000001.aaaaaa.a-step'

const ENTITIES: DiagramContextEntity[] = [
  {
    artifact_id: ENTITY_ID,
    name: 'A step',
    artifact_type: 'action',
    domain: 'business',
    status: 'draft',
    version: '0.1.0',
    host_diagram_id: null,
  } as unknown as DiagramContextEntity,
]

/**
 * One mapped shape plus a bare background rect the mapping never claims — the two things a click can
 * land on. `data-entity-id` is set by the composable, so the markup here carries only what a renderer
 * would emit.
 */
const SVG = `<svg xmlns="http://www.w3.org/2000/svg">
  <rect class="bg" width="400" height="300"></rect>
  <g id="step-a"><rect width="80" height="40"></rect><text>A step</text></g>
</svg>`

const harness = () => {
  const svgHtml = ref<string | null>(SVG)
  const container = document.createElement('div')
  container.innerHTML = SVG
  document.body.appendChild(container)

  const svc = {
    getEntity: vi.fn(() => Effect.succeed({ artifact_id: ENTITY_ID, name: 'A step' })),
  }
  const detail = ref<DiagramSvgSelectionDetail>({ diagram_type: 'activity' })

  let selection!: ReturnType<typeof useDiagramSvgSelection>
  const app = createApp(
    defineComponent({
      setup() {
        selection = useDiagramSvgSelection({
          svc: svc as never,
          router: { push: vi.fn() } as never,
          svgHtml,
          detail,
          diagramEntities: ref(ENTITIES),
          diagramConnections: ref([] as DiagramConnection[]),
          drilldownByEntityId: ref({}),
          diagramId: ref('DGM@1'),
          reload: vi.fn(),
        })
        selection.svgContainer.value = container
        return () => null
      },
    }),
  )
  app.mount(document.createElement('div'))
  return { selection, unmount: () => app.unmount() }
}

describe('deselecting a diagram entity', () => {
  it('keeps the selection when the same entity is clicked again', async () => {
    const { selection } = harness()
    selection.selectEntity(ENTITY_ID)
    await nextTick()
    expect(selection.selectedId.value).toBe(ENTITY_ID)

    selection.selectEntity(ENTITY_ID)
    await nextTick()

    expect(selection.selectedId.value).toBe(ENTITY_ID)
    expect(selection.hasSelection.value).toBe(true)
  })

  it('clears everything on `clearSelection`', async () => {
    const { selection } = harness()
    selection.selectEntity(ENTITY_ID)
    await nextTick()

    selection.clearSelection()
    await nextTick()

    expect(selection.selectedId.value).toBeNull()
    expect(selection.hasSelection.value).toBe(false)
  })

  it('reports nothing selected before the reader has clicked anything', () => {
    const { selection } = harness()
    expect(selection.hasSelection.value).toBe(false)
  })

})
