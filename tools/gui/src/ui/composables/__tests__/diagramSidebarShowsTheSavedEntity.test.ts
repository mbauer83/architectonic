// @vitest-environment jsdom
//
// After an edit saved from a diagram's sidebar, the sidebar shows what was saved.
//
// The regression: the sidebar's editor asked the view to reload, and the view reloaded the *diagram*.
// The panel renders the selected entity's own read, which nothing re-ran, so a changed summary or
// attribute went on showing its old value until the reader selected something else and came back.

import { describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, nextTick, ref } from 'vue'
import { Effect } from 'effect'
import { useDiagramSvgSelection, type DiagramSvgSelectionDetail } from '../useDiagramSvgSelection'
import type { DiagramConnection, DiagramContextEntity } from '../../../domain'

const ENTITY_ID = 'APP@1000000001.aaaaaa.a-component'

const flush = async () => { for (let i = 0; i < 4; i += 1) await Promise.resolve(); await nextTick() }

const harness = () => {
  let stored = 'before the save'
  const svc = {
    getEntity: vi.fn(() => Effect.sync(() => ({ artifact_id: ENTITY_ID, name: 'A component', summary: stored }))),
  }
  const reload = vi.fn()
  let selection!: ReturnType<typeof useDiagramSvgSelection>
  createApp(defineComponent({
    setup() {
      selection = useDiagramSvgSelection({
        svc: svc as never,
        router: { push: vi.fn() } as never,
        svgHtml: ref<string | null>(null),
        detail: ref<DiagramSvgSelectionDetail>({ diagram_type: 'archimate' }),
        diagramEntities: ref([] as DiagramContextEntity[]),
        diagramConnections: ref([] as DiagramConnection[]),
        drilldownByEntityId: ref({}),
        diagramId: ref('DGM@1'),
        reload,
      })
      return () => null
    },
  })).mount(document.createElement('div'))
  return { selection, reload, save: (summary: string) => { stored = summary } }
}

const shownSummary = (selection: ReturnType<typeof useDiagramSvgSelection>) =>
  (selection.entityQuery.data.value as { summary?: string } | null)?.summary

describe('a sidebar edit on a diagram', () => {
  it('re-reads the selected entity, so the panel shows the saved values', async () => {
    const { selection, save } = harness()
    selection.selectEntity(ENTITY_ID)
    await flush()
    expect(shownSummary(selection)).toBe('before the save')

    save('after the save')
    selection.entityEdited()
    await flush()

    expect(shownSummary(selection)).toBe('after the save')
    expect(selection.selectedId.value).toBe(ENTITY_ID)
  })

  it('still reloads the diagram, whose labels may show what changed', () => {
    const { selection, reload } = harness()
    selection.selectEntity(ENTITY_ID)

    selection.entityEdited()

    expect(reload).toHaveBeenCalledOnce()
  })

  it('reads nothing when nothing is selected', () => {
    const { selection } = harness()

    selection.entityEdited()

    expect(selection.entityQuery.data.value).toBeNull()
  })
})
