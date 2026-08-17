import { expect, test, type Page } from '@playwright/test'
import {
  capture, captureAnimation, captureRenderedDiagram, captureStoredDiagram, diagramById,
  gotoAndCapture, watch, type CaptureProvenance,
} from './mediaHelpers'

const BACKEND = 'APP@1777293133.OYEmP1.architecture-backend'
const ANALYSIS = 'STPA@1784721732.pflr.3e4395'
const STRATEGY = 'ARC@1784483951.yBNaaU.strategy-overview'
const VALUE_STREAM = 'ARC@1784483996.YRywG6.value-stream-deliver-an-architecture-aligned-change'
const INVESTMENT = 'ARC@1784488894.WwyJAa.resource-investment-map'
const C4_CONTEXT = 'CSC@1780829783.z8RRON.amp-system-context'
const C4_CONTAINERS = 'CC@1780829785.Z_fI-N.amp-containers'
//: The backend is drawn one concern at a time rather than all at once, so the figure shows
//: the write path — the concern the platform's central decision is about.
const C4_COMPONENTS = 'CC@1786952709.BT0ZHFR.architecture-backend-write-path'
const DATATYPE = 'DATATY@1782085920.9Nrbqf.artifact-persistence-model'
//: A viewpoint whose query has something in most of its sections. `goal-realization` was the first
//: choice and was the wrong one: it declares one condition and nothing else, so the figure was four
//: "No X declared" placeholders with the single interesting line buried among them. Impact analysis
//: asks for a parameter, derives a value from the neighbourhood and follows connections — which is
//: the grammar doing something worth photographing.
const QUERY_VIEWPOINT = 'element-dependents'

const provenance = (testName: string, artifactIds: readonly string[] = []): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: artifactIds,
  synthetic_augmentation: false,
})

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'uncategorized')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
    localStorage.setItem('arch_group_document-collection', 'uncategorized')
  })
})

test('application entities catalog', async ({ page }) => {
  await gotoAndCapture(page, '/entities?domain=application&group=platform-core', 'entities-list.png',
    provenance('application entities catalog'))
})

const HERO_VIEWPOINT = 'intent-to-implementation'
const HERO_ANCHOR = 'REQ@1712870400.peinbQ.tool-interfaces-mcp-cli-rest'
const HERO_SIDEBAR_NODE = 'Architecture MCP Endpoint'

test('hero intent-to-implementation exploration', async ({ page }) => {
  // The first image a visitor sees has to show the product's actual claim: a typed graph
  // whose relationships are the point, and a node that resolves to a real record. A table
  // shows neither. The population is deliberately one requirement's realization chain —
  // large enough to read as a real model, small enough that every label stays legible.
  const problems = watch(page)
  await page.goto(
    `/graph?viewpoint=${HERO_VIEWPOINT}&param.anchor=${encodeURIComponent(HERO_ANCHOR)}`,
    { waitUntil: 'load' },
  )

  await expect(page.locator('.graph-node')).toHaveCount(10)
  // Three domain clusters are what makes the figure read as cross-layer rather than as a
  // flat blob; the chips are the legend that says so.
  await expect(page.locator('.domain-chip')).toHaveCount(3)
  await page.locator('.graph-node').filter({ hasText: HERO_SIDEBAR_NODE }).first().click()
  await expect(page.locator('.graph-sidebar')).toContainText('application-component')

  await capture(page, 'hero-overview.png', {
    ...provenance('hero intent-to-implementation exploration'),
    viewpoint_slug: HERO_VIEWPOINT,
    parameters: { anchor: HERO_ANCHOR },
  })
  expect(problems, 'runtime problems while capturing hero-overview.png').toEqual([])
})

test('strategy overview diagram', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'strategy-overview.png', STRATEGY,
    'Architecture Knowledge Management', provenance('strategy overview diagram', [STRATEGY]))
})

test('architecture-aligned change value stream', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'value-stream-deliver-change.png', VALUE_STREAM,
    'Deliver an Architecture-Aligned Change', provenance('architecture-aligned change value stream', [VALUE_STREAM]))
})

test('resource investment map', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'resource-investment-map.png', INVESTMENT,
    'Resource Investment Map', provenance('resource investment map', [INVESTMENT]))
})

test('C4 system context', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'c4-context.png', C4_CONTEXT,
    'AMP &#8212; System Context', provenance('C4 system context', [C4_CONTEXT]))
})

test('C4 containers', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'c4-containers.png', C4_CONTAINERS,
    'AMP &#8212; Containers', provenance('C4 containers', [C4_CONTAINERS]))
})

test('C4 backend components', async ({ page, request }) => {
  await captureRenderedDiagram(page, request, 'c4-backend-components.png', C4_COMPONENTS,
    'Architecture Backend &#8212; Write Path', provenance('C4 backend components', [C4_COMPONENTS]))
})

test('re-shoot overview', async ({ page }) => {
  await gotoAndCapture(page, '/', 'overview.png', provenance('re-shoot overview'))
})

test('re-shoot search', async ({ page }) => {
  await gotoAndCapture(page, '/search?q=architecture', 'search.png', provenance('re-shoot search'))
})

test('re-shoot treemap', async ({ page }) => {
  await gotoAndCapture(page, '/entities?view=treemap&group=platform-core', 'treemap.png',
    provenance('re-shoot treemap'))
})

test('re-shoot entity detail', async ({ page }) => {
  await gotoAndCapture(page, `/entities/${encodeURIComponent(BACKEND)}`, 'entity-detail.png',
    provenance('re-shoot entity detail', [BACKEND]))
})

test('re-shoot group management', async ({ page }) => {
  await gotoAndCapture(page, '/entities/groups', 'group-management.png', provenance('re-shoot group management'))
})

test('re-shoot ArchiMate diagram', async ({ page, request }) => {
  const id = 'ARC@1777452513.68ZZDj.promote-artifacts'
  await captureRenderedDiagram(page, request, 'diagram-archimate.png', id,
    'Artifacts Promoted', provenance('re-shoot ArchiMate diagram', [id]))
})

test('re-shoot matrix diagram', async ({ page, request }) => {
  const id = 'MAT@1784484071.Vyfzpw.capabilities-value-stream-stages'
  await captureStoredDiagram(page, request, 'diagram-matrix.png', id,
    provenance('re-shoot matrix diagram', [id]))
})

test('re-shoot activity diagram', async ({ page, request }) => {
  const id = 'ACT@1781338474.NTuMXo.promote-engagement-work-to-the-enterprise-baseline'
  await captureStoredDiagram(page, request, 'diagram-activity.png', id,
    provenance('re-shoot activity diagram', [id]))
})

test('re-shoot sequence diagram', async ({ page, request }) => {
  const id = 'SEQ@1781338373.XPtsGv.from-a-write-to-a-consistent-broadcast-state'
  await captureStoredDiagram(page, request, 'diagram-sequence.png', id,
    provenance('re-shoot sequence diagram', [id]))
})

test('re-shoot C4 diagram', async ({ page, request }) => {
  await captureStoredDiagram(page, request, 'diagram-c4.png', C4_CONTAINERS,
    provenance('re-shoot C4 diagram', [C4_CONTAINERS]))
})

async function captureAssurance(
  page: Page, route: string, fileName: string, name: string, artifactIds: readonly string[] = [],
): Promise<void> {
  const problems = watch(page)
  await page.goto(route, { waitUntil: 'load' })
  // Wait for whichever shell this assurance surface renders once its own load settles: the browse
  // nav, a diagram canvas, a client-side grid, or a wizard. This used to wait for the hub page's
  // "Loading assurance store status" to disappear; the hub is gone and that text with it, so the
  // wait had become a no-op that passed instantly — and then, narrowed to the browse and diagram
  // shells, it excluded the wizards, which is what the GSN figure is one of.
  await expect(
    page.locator('.wizard-nav, .wizard, .diagram-grid, .svg-wrap, .uca-matrix, .fmea-table').first(),
  ).toBeVisible({ timeout: 10_000 })
  await capture(page, fileName, provenance(name, artifactIds))
  expect(problems, `runtime problems while capturing ${fileName}`).toEqual([])
}

test('re-shoot assurance overview', async ({ page }) => {
  await captureAssurance(page, '/assurance', 'assurance-overview.png', 're-shoot assurance overview')
})

test('re-shoot assurance control structure', async ({ page }) => {
  // A derived diagram is scoped to an analysis, so the URL names both halves. The old
  // `/assurance/diagrams?type=…` shot the catalog page with an ignored query.
  await captureAssurance(page, `/assurance/analyses/${encodeURIComponent(ANALYSIS)}/diagrams/control-structure`,
    'assurance-control-structure.png', 're-shoot assurance control structure', [ANALYSIS])
})

test('re-shoot assurance bowtie', async ({ page }) => {
  await captureAssurance(page, `/assurance/analyses/${encodeURIComponent(ANALYSIS)}/diagrams/bowtie`,
    'assurance-bowtie.png', 're-shoot assurance bowtie', [ANALYSIS])
})

test('re-shoot assurance GSN', async ({ page }) => {
  await captureAssurance(page, `/assurance/analyses/${encodeURIComponent(ANALYSIS)}/gsn`,
    'assurance-gsn.png', 're-shoot assurance GSN', [ANALYSIS])
})

const WALK_ANCHOR = 'REQ@1712870400.eBAa26.graph-based-relationship-discovery'

test('re-shoot graph exploration walk', async ({ page }) => {
  // The figure has to show the thing the surrounding prose claims — that you start somewhere
  // and walk outward — so it is an actual traversal: open on a requirement, expand a
  // neighbour into its own neighbourhood, expand once more, then open a node's record. A
  // still of a finished graph would show the result and none of the walking.
  const problems = watch(page)
  const nodes = page.locator('.graph-node')

  const expandNeighbour = async (): Promise<void> => {
    const before = await nodes.count()
    // Whichever unexpanded neighbour has the most to contribute: picking by index gives a
    // different figure every time the model grows, and often a leaf that adds nothing.
    const target = nodes.filter({ has: page.locator('.expand-badge') }).first()
    await target.dispatchEvent('dblclick')
    await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  }

  await captureAnimation(page, 'graph-explore.gif',
    provenance('re-shoot graph exploration walk', [WALK_ANCHOR]), [
      {
        name: 'open',
        act: async () => {
          await page.goto(`/entities/${encodeURIComponent(WALK_ANCHOR)}/graph`, { waitUntil: 'load' })
          // Attached is not drawn: the first frame used to be blank canvas with "Loading…" still in
          // the sidebar, so the figure opened on the one state that shows nothing. Wait for a node
          // to be visible and for the sidebar to have finished before the first beat is shot.
          await expect(nodes.first()).toBeVisible({ timeout: 20_000 })
          await expect(page.getByText(/^\s*Loading\b.*(…|\.\.\.)\s*$/)).toHaveCount(0, { timeout: 20_000 })
        },
      },
      { name: 'expand-once', act: expandNeighbour },
      { name: 'expand-twice', act: expandNeighbour },
      {
        name: 'cluster',
        act: async () => {
          const cluster = page.getByRole('button', { name: 'Cluster', exact: true })
          await cluster.click()
          await expect(cluster).toHaveClass(/spacing-btn--active/)
        },
      },
      {
        name: 'inspect',
        act: async () => {
          await nodes.nth(1).dispatchEvent('click')
          await expect(page.locator('.graph-sidebar')).not.toContainText('Click a node or edge')
        },
      },
    ])

  expect(problems, 'runtime problems while capturing graph-explore.gif').toEqual([])
})


test('datatype diagram with an attribute selected', async ({ page, request }) => {
  // The figure the datatype docs lacked. A datatype diagram's point is that a classifier's
  // attributes are themselves addressable — each row carries its type, multiplicity, key
  // membership and provenance — and that is only visible with one selected, so the shot has to
  // include the sidebar. A picture of the boxes alone shows a class diagram, which undersells it.
  const problems = watch(page)
  const diagram = await diagramById(request, DATATYPE)
  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
  await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 15_000 })

  // `[data-subpart]` is the marker the datatype extension stamps on each attribute row; picking a
  // row by index would drift as the model gains fields.
  const attribute = page.locator('.svg-wrap [data-subpart]').first()
  await expect(attribute).toBeVisible({ timeout: 15_000 })
  // Dispatched, not `.click()`: the row is an SVG group inside the pan/zoom surface, and a real
  // pointer click lands on whatever the viewer overlays for dragging. The graph specs dispatch for
  // the same reason.
  await attribute.dispatchEvent('click')

  // Assert the attribute panel actually filled before shooting, so a broken selection produces a
  // failing test rather than a figure of an empty sidebar. `.ent-det` is what the datatype
  // extension's sub-part detail renders as inside the generic sidebar.
  const detail = page.locator('.sidebar .ent-det').first()
  await expect(detail, 'the selected attribute must show its detail').toBeVisible({ timeout: 10_000 })
  await expect(detail.locator('.det-name')).not.toBeEmpty()

  await capture(page, 'diagram-datatype-attribute.png',
    provenance('datatype diagram with an attribute selected', [DATATYPE]))
  expect(problems, 'runtime problems while capturing diagram-datatype-attribute.png').toEqual([])
})

test('viewpoint query tab', async ({ page }) => {
  // Shot from an existing viewpoint rather than a draft: a freshly created one has an empty query,
  // and a figure of empty form controls teaches nobody what the grammar expresses.
  const problems = watch(page)
  await page.goto(`/viewpoints/${QUERY_VIEWPOINT}/edit`, { waitUntil: 'load' })
  await page.getByRole('button', { name: 'Query' }).click()

  // Both clauses this viewpoint is chosen for must be on screen, or the figure is of a tab rather
  // than of a query. The headings are the reader-facing ones the tab renders, not the wire names.
  await expect(page.getByRole('heading', { name: 'Show entities where…' }))
    .toBeVisible({ timeout: 15_000 })
  // Populated, not merely present: a figure of empty placeholder prose teaches nobody the grammar,
  // which is exactly what the first choice of viewpoint produced.
  await expect(page.getByRole('heading', { name: 'Parameters' })).toBeVisible()
  await expect(
    page.getByText('No parameters declared', { exact: false }),
    'the chosen viewpoint must actually declare a parameter',
  ).toHaveCount(0)
  await capture(page, 'viewpoint-query-tab.png',
    provenance('viewpoint query tab', [QUERY_VIEWPOINT]))
  expect(problems, 'runtime problems while capturing viewpoint-query-tab.png').toEqual([])
})
