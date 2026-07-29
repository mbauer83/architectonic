// @vitest-environment jsdom
//
// Marking the selection on a rendered assurance SVG.
//
// Regression: clicking a node opened its detail panel while the diagram itself gave no sign of
// which node the panel described — the selection was state without an appearance. Re-rendering
// the projection (a new SVG element) must also re-apply the mark, or the highlight silently
// disappears while the panel stays open.
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h, createApp, ref } from 'vue'
import { SELECTED_CLASS, useAssuranceSvgInteractions } from '../useAssuranceSvgInteractions'
import type {
  AssuranceDiagramEdge,
  AssuranceDiagramNode,
  NodeRepresentingEdge,
} from '../../components/AssuranceDiagramPanel.helpers'

const NODES: AssuranceDiagramNode[] = [
  { node_id: 'CSN@1', node_type: 'control-structure-node', name: 'Controller' },
  { node_id: 'CA@2', node_type: 'control-action', name: 'Apply brake' },
]
const EDGES: AssuranceDiagramEdge[] = [
  { edge_id: 'E1', source_id: 'CSN@1', target_id: 'CA@2', conn_type: 'issues' },
]
/** As the renderer publishes it: the PlantUML alias each node was drawn under, mapped to its id. */
const NODE_ALIASES: Record<string, string> = { N_CSN_1: 'CSN@1', N_CA_2: 'CA@2' }

const svgMarkup = () => `
  <svg>
    <g data-assurance-node-id="CSN@1"><rect/></g>
    <g data-assurance-node-id="CA@2"><polygon/></g>
    <g data-assurance-edge-id="E1"><path/></g>
  </svg>`

/** Drive the composable inside a real component instance (it registers onUnmounted). */
const withComposable = (run: (api: ReturnType<typeof useAssuranceSvgInteractions>, container: HTMLElement) => void) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const Harness = defineComponent({
    setup() {
      const svgContainer = ref<HTMLElement | null>(null)
      const api = useAssuranceSvgInteractions({
        svgContainer,
        nodes: ref(NODES),
        edges: ref(EDGES),
        nodeAliases: ref(NODE_ALIASES),
        onSelectNode: () => {},
        onSelectEdge: () => {},
      })
      const container = document.createElement('div')
      container.innerHTML = svgMarkup()
      svgContainer.value = container
      run(api, container)
      return () => h('div')
    },
  })
  const app = createApp(Harness)
  app.mount(host)
  app.unmount()
  document.body.innerHTML = ''
}

const markedIds = (container: HTMLElement): string[] =>
  [...container.querySelectorAll(`.${SELECTED_CLASS}`)].map(
    (el) => el.getAttribute('data-assurance-node-id') ?? el.getAttribute('data-assurance-edge-id') ?? '?',
  )

describe('markSelection', () => {
  it('marks the selected node and only that node', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ nodeId: 'CA@2' })
      expect(markedIds(container)).toEqual(['CA@2'])
    })
  })

  it('moves the mark rather than accumulating marks', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ nodeId: 'CSN@1' })
      markSelection({ nodeId: 'CA@2' })
      expect(markedIds(container)).toEqual(['CA@2'])
    })
  })

  it('marks a selected edge', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ edgeId: 'E1' })
      expect(markedIds(container)).toEqual(['E1'])
    })
  })

  it('clears the mark when nothing is selected', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ nodeId: 'CSN@1' })
      markSelection({ nodeId: null, edgeId: null })
      expect(markedIds(container)).toEqual([])
    })
  })

  it('re-marks after the projection is re-rendered into a fresh SVG', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ nodeId: 'CA@2' })
      container.innerHTML = svgMarkup()
      expect(markedIds(container)).toEqual([])

      markSelection({ nodeId: 'CA@2' })
      expect(markedIds(container)).toEqual(['CA@2'])
    })
  })

  it('tolerates an id that is not in the rendered projection', () => {
    withComposable(({ markSelection }, container) => {
      markSelection({ nodeId: 'HAZ@not-drawn' })
      expect(markedIds(container)).toEqual([])
    })
  })

  it('does not break on an id containing characters that are special in a selector', () => {
    withComposable(({ markSelection }, container) => {
      const group = container.querySelector('[data-assurance-node-id="CA@2"]')!
      group.setAttribute('data-assurance-node-id', 'CA@2.a:b')
      markSelection({ nodeId: 'CA@2.a:b' })
      expect(markedIds(container)).toEqual(['CA@2.a:b'])
    })
  })
})

/**
 * A control action is drawn as the arrow from its controller to what it acts on (the STPA
 * notation), but it remains an entity carrying UCAs, TLP, status, and an architecture binding —
 * so that arrow has to select the *action*. If it did not, drawing the diagram correctly would
 * make the action unreachable.
 */
const CONTROL_STRUCTURE_NODES: AssuranceDiagramNode[] = [
  { node_id: 'CSN@ctl', node_type: 'control-structure-node', name: 'Controller' },
  { node_id: 'CSN@proc', node_type: 'control-structure-node', name: 'Process' },
  { node_id: 'CA@brake', node_type: 'control-action', name: 'Apply brake' },
]
const CONTROL_STRUCTURE_EDGES: AssuranceDiagramEdge[] = [
  { edge_id: 'E-issues', source_id: 'CSN@ctl', target_id: 'CA@brake', conn_type: 'issues' },
  { edge_id: 'E-acts', source_id: 'CA@brake', target_id: 'CSN@proc', conn_type: 'acts-on' },
  { edge_id: 'E-fb', source_id: 'CSN@ctl', target_id: 'CSN@proc', conn_type: 'feedback' },
]
const LINKS: NodeRepresentingEdge[] = [
  { node_id: 'CA@brake', source_id: 'CSN@ctl', target_id: 'CSN@proc' },
]

/** How PlantUML emits the collapsed structure: two boxes, a down arrow, and a feedback arrow. */
/** The aliases in `collapsedSvg` below, as the renderer would publish them. */
const CONTROL_STRUCTURE_ALIASES: Record<string, string> = {
  N_CSN_ctl: 'CSN@ctl', N_CSN_proc: 'CSN@proc', N_CA_brake: 'CA@brake',
}

const collapsedSvg = () => `
  <svg>
    <g class="entity" id="ent1"><title>N_CSN_ctl</title><rect/></g>
    <g class="entity" id="ent2"><title>N_CSN_proc</title><rect/></g>
    <g class="link" data-entity-1="ent1" data-entity-2="ent2"><path/></g>
    <g class="link" data-entity-1="ent2" data-entity-2="ent1"><path/></g>
  </svg>`

const withControlStructure = async (
  run: (api: ReturnType<typeof useAssuranceSvgInteractions>, container: HTMLElement) => Promise<void> | void,
) => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  // `setup()` runs synchronously inside `app.mount()` below, but the compiler cannot see that —
  // so this starts undefined, which `await` handles.
  let pending: Promise<void> | undefined
  const Harness = defineComponent({
    setup() {
      const svgContainer = ref<HTMLElement | null>(null)
      const api = useAssuranceSvgInteractions({
        svgContainer,
        nodes: ref(CONTROL_STRUCTURE_NODES),
        edges: ref(CONTROL_STRUCTURE_EDGES),
        nodeAliases: ref(CONTROL_STRUCTURE_ALIASES),
        nodeRepresentingEdges: ref(LINKS),
        onSelectNode: (nodeId) => selectedNodes.push(nodeId),
        onSelectEdge: (edge) => selectedEdges.push(edge.edge_id ?? ''),
      })
      const container = document.createElement('div')
      container.innerHTML = collapsedSvg()
      svgContainer.value = container
      pending = Promise.resolve(run(api, container))
      return () => h('div')
    },
  })
  const app = createApp(Harness)
  app.mount(host)
  await pending
  app.unmount()
  document.body.innerHTML = ''
}

let selectedNodes: string[] = []
let selectedEdges: string[] = []

describe('a control action drawn as an arrow', () => {
  beforeEach(() => {
    selectedNodes = []
    selectedEdges = []
  })

  it('tags the controller→process arrow with the control action it draws', async () => {
    await withControlStructure(async ({ attachInteractivity }, container) => {
      await attachInteractivity()
      const arrow = container.querySelector('.link[data-assurance-node-id]')
      expect(arrow?.getAttribute('data-assurance-node-id')).toBe('CA@brake')
    })
  })

  it('selects the action — not an edge — when that arrow is clicked', async () => {
    await withControlStructure(async ({ attachInteractivity }, container) => {
      await attachInteractivity()
      const arrow = container.querySelector<HTMLElement>('.link[data-assurance-node-id]')!
      arrow.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(selectedNodes).toEqual(['CA@brake'])
      expect(selectedEdges).toEqual([])
    })
  })

  it('leaves the reverse arrow as feedback, since direction is what distinguishes them', async () => {
    await withControlStructure(async ({ attachInteractivity }, container) => {
      await attachInteractivity()
      const feedback = container.querySelector<HTMLElement>('[data-assurance-edge-id]')!
      expect(feedback.getAttribute('data-assurance-edge-id')).toBe('E-fb')
      feedback.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(selectedEdges).toEqual(['E-fb'])
      expect(selectedNodes).toEqual([])
    })
  })

  it('highlights the arrow when its action is selected', async () => {
    await withControlStructure(async ({ attachInteractivity, markSelection }, container) => {
      await attachInteractivity()
      markSelection({ nodeId: 'CA@brake' })
      const marked = container.querySelector(`.${SELECTED_CLASS}`)
      expect(marked?.getAttribute('data-assurance-node-id')).toBe('CA@brake')
      expect(marked?.classList.contains('link')).toBe(true)
    })
  })
})
