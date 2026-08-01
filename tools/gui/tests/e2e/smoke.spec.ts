import { type Page } from '@playwright/test'

import { test, expect } from './coverage-fixture'

/**
 * Route-walk smoke test.
 *
 * For every GUI route we assert three runtime-wiring invariants that the unit suite
 * (which mocks dependencies) cannot see:
 *   1. no API request returns 5xx      — catches backend/runtime regressions
 *   2. no uncaught page error          — catches the blank-page render crash
 *   3. <main> renders non-empty text   — catches "header only" blanks
 *
 * Detail routes are reached by clicking the first item in their list view so we never
 * hard-code artifact ids and we exercise the real `/api/ontology/classification` and
 * `/api/diagrams/{artifact_id}/context` calls that the 422 bug broke.
 */

type Problem = { kind: string; detail: string }
type DiagramSummary = { artifact_id: string; name: string; diagram_type: string }
type DiagramList = { items: DiagramSummary[] }
type DiagramEntity = { artifact_id: string; name: string; artifact_type: string }
type DiagramContext = {
  diagram: { diagram_entities?: unknown }
  entities: DiagramEntity[]
}

// Seed the per-axis "active group" keys so list views behave like a returning user and
// render their lists, instead of the first-visit redirect to the group-management page.
test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    localStorage.setItem('arch_group_diagram-collection', 'uncategorized')
    localStorage.setItem('arch_group_document-collection', 'uncategorized')
  })
})

// The browser auto-logs "Failed to load resource: the server responded with a status
// of 423 (Locked)" for assurance endpoints whenever the confidential assurance store
// is locked — the intended state in CI (and any env that hasn't unlocked it). The app
// handles 423 explicitly and renders a "Store is locked" message, so this is an
// expected, gracefully-handled condition, not a runtime problem. HTTP-status health is
// owned by the response listener below (scoped to 5xx), so suppressing this one echo —
// tightly bound to status 423 on an /api/assurance resource — masks nothing else.
function isExpectedLockedAssuranceEcho(msg: { text(): string; location(): { url: string } }): boolean {
  return /Failed to load resource.*status of 423/.test(msg.text())
    && msg.location().url.includes('/api/assurance')
}

function watch(page: Page): { problems: Problem[] } {
  const problems: Problem[] = []
  page.on('pageerror', (err) => problems.push({ kind: 'pageerror', detail: String(err) }))
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    if (isExpectedLockedAssuranceEcho(msg)) return
    problems.push({ kind: 'console.error', detail: msg.text() })
  })
  page.on('response', (resp) => {
    const url = resp.url()
    if (url.includes('/api/') && resp.status() >= 500) {
      problems.push({ kind: `http ${resp.status()}`, detail: url })
    }
  })
  return { problems }
}

async function expectHealthyMain(page: Page, problems: Problem[]): Promise<void> {
  const main = page.locator('#app > main')
  await expect(main).toBeVisible()
  const text = (await main.innerText()).trim()
  expect(text.length, 'main content should not be empty (header-only blank)').toBeGreaterThan(0)
  expect(problems, `runtime problems:\n${problems.map((p) => `  [${p.kind}] ${p.detail}`).join('\n')}`).toEqual([])
}

/**
 * Click a rendered SVG entity node and return the name shown in the detail sidebar.
 *
 * Robustness notes (this was a recurring CI-only flake):
 *  - Prefer leaf nodes (`:not(.cluster)`). A cluster is a large boundary box whose
 *    interior is legitimately crossed by edges and child nodes, so its geometric
 *    centre — where Playwright clicks a <g> — is often covered by a connection's
 *    wide transparent hit-area (`data-conn-hit`, pointer-events="stroke"), which
 *    intercepts the click. Graphviz lays diagrams out slightly differently in CI
 *    than locally, so the overlap only ever bit in CI. Leaf nodes meet their edges
 *    at the border, leaving the centre clickable.
 *  - Verify a *real entity* was selected via `a.det-name`: the entity detail renders
 *    its name as a RouterLink (<a>), whereas a connection detail renders a <span>.
 *    Keying off `.det-name` alone would pass even if a stray click hit an edge.
 *  - Try candidates in turn so a single overlapped node cannot fail the whole test.
 */
/**
 * Click nodes until one populates the sidebar, and return the name it showed.
 *
 * The name is matched as `.det-name` rather than `a.det-name`, because whether it is a link is a
 * property of the entity and not of the sidebar: a repository-backed entity links to its own page,
 * while a **diagram-only** entity has no page to link to and renders a static span. Every GSN node is
 * diagram-only, so the link-only selector this used could never match one — the test failed for
 * asserting the app was wrong about something the app had right. The distinction itself is asserted
 * at each call site below, so broadening the selector here does not lose it.
 */
async function clickEntityNodeForDetail(page: Page, label: string): Promise<string> {
  await page.waitForSelector('.svg-wrap [data-entity-id]', { timeout: 15_000 })
  const leaves = page.locator('.svg-wrap [data-entity-id]:not(.cluster)')
  const candidates = (await leaves.count()) > 0 ? leaves : page.locator('.svg-wrap [data-entity-id]')
  const entityName = page.locator('.ent-det .det-hdr .det-name')
  const count = await candidates.count()
  let lastErr: unknown
  for (let i = 0; i < count; i++) {
    try {
      await candidates.nth(i).click({ timeout: 10_000 })
      await expect(entityName).toBeVisible({ timeout: 5_000 })
      const text = (await entityName.textContent())?.trim() ?? ''
      if (text.length > 0) return text
    } catch (err) {
      lastErr = err
    }
  }
  throw new Error(`${label}: no entity node click populated the detail sidebar (${count} candidates): ${String(lastErr)}`)
}

const STATIC_ROUTES = [
  '/',
  '/entities',
  '/entities?domain=motivation',
  '/entities/groups',
  '/documents',
  '/diagrams',
  '/viewpoints',
  '/viewpoints/matrix',
  '/viewpoints/diagram',
  // A viewpoint population large enough to aggregate: the exploration renders synthetic
  // cluster super-nodes alongside real entities, and anything that treats one as a
  // lookupable entity shows up here as a 404 the route-walk refuses.
  '/graph?viewpoint=application-usage',
  '/search',
  '/promote',
  '/assurance',
  // Kept in the walk on purpose: it is the former path of the browse surface, and the redirect
  // that keeps old links and bookmarks working has to keep working too.
  '/assurance/browse',
  '/assurance/graph',
  '/assurance/analyses',
  '/assurance/stpa',
  '/assurance/grc',
  '/assurance/cast',
  '/assurance/gsn',
  '/assurance/supply-chain',
  '/assurance/baselines',
  '/assurance/fmea',
  '/assurance/fmea/new',
  '/assurance/diagrams',
  // No `?analysis=…&type=…` here: a derived diagram is scoped to an analysis, and the ids in this
  // store are not knowable to a static list. The unselected page has to render cleanly too, and the
  // populated case is walked below by clicking a card in the catalog.
  '/assurance/diagram',
  '/global/entities',
  '/global/diagrams',
]

for (const route of STATIC_ROUTES) {
  test(`route renders cleanly: ${route}`, async ({ page }) => {
    const { problems } = watch(page)
    await page.goto(route, { waitUntil: 'load' })
    await page.waitForTimeout(1500)
    await expectHealthyMain(page, problems)
  })
}

test('assurance node deep link: unknown id renders the indistinguishable not-found page', async ({ page }) => {
  // The 404 echo is expected here (unknown OR above-ceiling — by design the same);
  // suppress exactly that one console line and keep every other problem fatal.
  const problems: Problem[] = []
  page.on('pageerror', (err) => problems.push({ kind: 'pageerror', detail: String(err) }))
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    if (isExpectedLockedAssuranceEcho(msg)) return
    if (/Failed to load resource.*status of 404/.test(msg.text()) && msg.location().url.includes('/api/assurance/nodes/')) return
    problems.push({ kind: 'console.error', detail: msg.text() })
  })
  await page.goto('/assurance/node/HAZ%40does-not-exist', { waitUntil: 'load' })
  await page.waitForTimeout(1500)
  const main = page.locator('#app > main')
  await expect(main).toBeVisible()
  const text = (await main.innerText()).trim()
  // Locked store (CI default) shows the locked banner; unlocked shows not-found —
  // both are healthy, explicit states for a deep link that cannot resolve.
  expect(/does not exist|locked/i.test(text), `unexpected page text: ${text}`).toBe(true)
  expect(problems, `runtime problems:\n${problems.map((p) => `  [${p.kind}] ${p.detail}`).join('\n')}`).toEqual([])
})

test('entity detail renders (exercises the ontology connection editor)', async ({ page }) => {
  const { problems } = watch(page)
  await page.goto('/entities', { waitUntil: 'load' })
  const firstEntity = page.locator('main a[href*="/entities/"]').first()
  await firstEntity.waitFor({ timeout: 10000 })
  await firstEntity.click()
  await page.waitForTimeout(2000)
  await expectHealthyMain(page, problems)
})

test('empty uncategorized group does not show stale ungrouped entities', async ({ page }) => {
  const { problems } = watch(page)
  await page.goto('/entities?group=uncategorized', { waitUntil: 'load' })
  await expect(page.getByRole('heading', { name: /Entities\s+\(0\)/ })).toBeVisible()
  await expect(page.getByText('No entities in "Uncategorized" yet.')).toBeVisible()
  await expect(page.locator('main a[href*="/entities/"]')).toHaveCount(0)
  await expectHealthyMain(page, problems)
})

test('entity detail shows documents that reference the entity', async ({ page }) => {
  const { problems } = watch(page)
  await page.goto(
    '/entities/REQ%401712870400.Kk6Ll6.verified-unique-identifiers-for-entities-connections-diagrams-and-documents',
    { waitUntil: 'load' },
  )
  await expect(page.getByText('Referenced in documents')).toBeVisible()
  await expect(page.getByRole('link', {
    name: 'Artifact Identity: Typed Epoch-Random Identifiers in Filenames; Grouping by Directory',
  })).toBeVisible()
  await expectHealthyMain(page, problems)
})

test('disabled SysML module is not offered in frontend module surfaces', async ({ page }) => {
  const { problems } = watch(page)
  const groupsModules = page.waitForResponse((resp) => resp.url().includes('/api/modules') && resp.ok())
  await page.goto('/entities/groups', { waitUntil: 'load' })
  await groupsModules
  await page.getByRole('button', { name: /\+ New project/i }).click()
  await expect(page.getByText('SysML v2')).toHaveCount(0)
  await expectHealthyMain(page, problems)

  const wizardModules = page.waitForResponse((resp) => resp.url().includes('/api/modules') && resp.ok())
  await page.goto('/model/wizard', { waitUntil: 'load' })
  await wizardModules
  await expect(page.getByText('SysML v2')).toHaveCount(0)
  await expectHealthyMain(page, problems)
})

test('every stored diagram instance renders (exercises each diagram type)', async ({ context, request }) => {
  test.setTimeout(180_000)
  const response = await request.get('/api/diagrams')
  expect(response.ok()).toBeTruthy()
  const diagrams = (await response.json() as DiagramList).items
  expect(diagrams.length, 'route walk needs at least one stored diagram').toBeGreaterThan(0)

  for (const diagram of diagrams) {
    await test.step(`${diagram.diagram_type}: ${diagram.name}`, async () => {
      // Assert the SVG actually renders. Navigating the page and checking health races the
      // lazy, ~1s /api/diagrams/{id}/svg call (which can outlast the health check), so a broken
      // diagram passed unnoticed; fetch the render endpoint directly and require success.
      // Matrix diagrams have no SVG representation — they render as Markdown in-page (mirrors
      // the frontend's diagramNeedsSvg), so the page health check below is their coverage.
      if (diagram.diagram_type !== 'matrix') {
        const svg = await request.get(`/api/diagrams/${encodeURIComponent(diagram.artifact_id)}/svg`)
        expect(svg.ok(), `${diagram.diagram_type} '${diagram.name}' failed to render: HTTP ${svg.status()}`).toBeTruthy()
      }

      const page = await context.newPage()
      const { problems } = watch(page)
      try {
        await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
        await page.locator('#app > main').waitFor()
        await page.waitForTimeout(300)
        await expectHealthyMain(page, problems)
      } finally {
        await page.close()
      }
    })
  }
})

test('C4 rendered labels contain names, retain person labels, and omit descriptions', async ({ page, request }) => {
  test.setTimeout(120_000)
  const response = await request.get('/api/diagrams')
  const diagrams = (await response.json() as DiagramList).items
    .filter((diagram) => diagram.diagram_type.startsWith('c4-'))
  expect(diagrams.length, 'C4 assertions require at least one stored C4 diagram').toBeGreaterThan(0)

  let personLabels = 0
  for (const diagram of diagrams) {
    const contextResponse = await request.get(`/api/diagrams/${encodeURIComponent(diagram.artifact_id)}/context`)
    expect(contextResponse.ok()).toBeTruthy()
    const context = await contextResponse.json() as DiagramContext
    const raw = context.diagram.diagram_entities
    const explicit = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
    const descriptions: string[] = []
    const explicitPersons = Array.isArray(explicit.person) ? explicit.person : []
    const modelPersons = context.entities.filter((entity) =>
      ['business-actor', 'business-role', 'role'].includes(entity.artifact_type),
    )
    const explicitLabels: string[] = []

    for (const value of Object.values(explicit)) {
      if (!Array.isArray(value)) continue
      for (const item of value) {
        if (!item || typeof item !== 'object') continue
        const record = item as Record<string, unknown>
        const description = String(record.description ?? '').trim()
        const label = String(record.label ?? '').trim()
        if (description) descriptions.push(description)
        if (label) explicitLabels.push(label)
      }
    }

    await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
    const svg = page.locator('.svg-wrap svg')
    await expect(svg).toBeVisible()
    const svgText = (await svg.textContent()) ?? ''

    for (const label of explicitLabels) expect(svgText).toContain(label)
    for (const description of descriptions) expect(svgText).not.toContain(description)
    for (const person of explicitPersons) {
      const label = String((person as Record<string, unknown>).label ?? '').trim()
      if (!label) continue
      expect(svgText).toContain(label)
      personLabels += 1
    }
    const renderedModelPersons = modelPersons.filter((person) => svgText.includes(person.name))
    personLabels += renderedModelPersons.length
  }
  expect(personLabels, 'C4 assertions require at least one rendered person label').toBeGreaterThan(0)
})

test('assurance rows render and visible TLP values have distinct colours', async ({ page, request }) => {
  const { problems } = watch(page)
  const response = await request.get('/api/assurance/nodes')
  expect(response.ok()).toBeTruthy()
  const body = await response.json() as { nodes: Array<{ tlp?: string }> }

  await page.goto('/assurance', { waitUntil: 'load' })
  await page.waitForTimeout(500)
  await expectHealthyMain(page, problems)
  // `.data-table__row`, not the `.node-item` this asserted for a while: the list became a DataTable
  // and the selector was never updated. It went unnoticed because of the guard that used to wrap
  // this line — with the store locked the API returns no nodes, so the count was skipped and the
  // test passed while asserting nothing. Unconditional now, and the emptiness is stated as its own
  // expectation so a locked store fails here rather than quietly agreeing.
  expect(body.nodes.length, 'unlock the store: this assertion is vacuous without content')
    .toBeGreaterThan(0)
  await expect(page.locator('.data-table__row')).toHaveCount(body.nodes.length)

  const chips = page.locator('.node-tlp')
  const coloursByTlp = new Map<string, string>()
  for (let index = 0; index < await chips.count(); index += 1) {
    const chip = chips.nth(index)
    coloursByTlp.set((await chip.innerText()).trim(), await chip.evaluate((el) => getComputedStyle(el).color))
  }
  // The published dogfood content is all publishable (≤ TLP:GREEN), so a single TLP value
  // is expected. Assert chips render and that *distinct* TLP values map to distinct colours
  // (the colour-coding contract) rather than requiring ≥2 levels the public seed can't carry.
  expect(coloursByTlp.size, 'assurance browse must render at least one TLP chip').toBeGreaterThan(0)
  expect(new Set(coloursByTlp.values()).size).toBe(coloursByTlp.size)
})

test('assurance-only diagrams are selectable on the unified surface', async ({ page, request }, testInfo) => {
  const { problems } = watch(page)
  const genericTypes = await request.get('/api/diagram-types')
  expect(genericTypes.ok()).toBeTruthy()
  const typeKeys = new Set((await genericTypes.json() as Array<{ key: string }>).map((item) => item.key))
  expect(typeKeys.has('gsn')).toBe(true)
  for (const assuranceType of ['bowtie', 'control-structure', 'uca-matrix']) {
    expect(typeKeys.has(assuranceType)).toBe(false)
  }

  // `.diagram-card`, not `.diagram-btn`: the picker became a card grid of RouterLinks and this
  // selector was left behind, so the step timed out looking for an element that no longer exists.
  // Returning to the picker inside the loop is part of the same rework — the cards navigate to a
  // detail route now, where a single-page picker used to swap the panel in place, so every iteration
  // after the first was looking for cards on the detail page.
  // `.first()` on every card locator below: a derived diagram belongs to an analysis, so the picker
  // lists one card per (analysis, type) pair. A second STPA in the store gives two Bowtie cards and
  // the bare locator was a strict-mode violation — the store gaining an analysis is the product
  // working, and this walk is about each type being reachable, not about how many analyses offer it.
  const openCard = async (title: string): Promise<void> => {
    await page.goto('/assurance/diagrams', { waitUntil: 'load' })
    await page.locator('.diagram-card', { hasText: title }).first().click()
  }

  // The node-selectable projections: a graph or matrix of assurance nodes, where picking one opens
  // the selection panel.
  for (const title of ['Bowtie', 'Control Structure', 'UCA Matrix']) {
    await test.step(title, async () => {
      await openCard(title)
      // `.svg-wrap`, not `.svg-container` — the third selector in this file left behind by a GUI
      // rework. All three went unnoticed because nothing runs this walk in the standard gates.
      const target = page.locator(
        '.svg-wrap [data-assurance-node-id], .diagram-fallback .fallback-item, .uca-matrix .node-link, .uca-matrix .uca-chip',
      ).first()
      await expect(target).toBeVisible()
      await target.click()
      await expect(page.locator('.selection-panel')).toBeVisible()
      await expect(page.getByText('Edit in Assurance Browse →')).toBeVisible()
    })
  }

  // The FMEA matrix is a worksheet, not a node projection: its cells are recording controls, and
  // it deliberately has no node selection. What it owes a reader is a way out to the element each
  // row is about — the walk asserted a selection panel it never had, and failed for it.
  await test.step('FMEA Matrix', async () => {
    await openCard('FMEA Matrix')
    await expect(page.locator('.fmea-table')).toBeVisible()
    const elementLink = page.locator('.fmea-table .fmea-element-link').first()
    await expect(elementLink).toBeVisible()
    await expect(elementLink).toHaveAttribute('href', /\/entity\?id=/)
    await elementLink.click()
    await expect(page).toHaveURL(/\/entity\?id=/)
    await expectHealthyMain(page, problems)
  })
  await expectHealthyMain(page, problems)
  const screenshot = testInfo.outputPath('t15-unified-assurance-diagram-selection.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T15 unified assurance diagram selection', {
    path: screenshot,
    contentType: 'image/png',
  })
})

test('assurance traceability matrix links model entities and wraps at word boundaries', async ({ page }) => {
  const matrixId = 'MAT@1780656830.v5cdp4.assurance-requirements-traceability'
  await page.goto(`/diagrams/${encodeURIComponent(matrixId)}`, { waitUntil: 'load' })

  const serviceLink = page.getByRole('link', { name: 'Assurance Service', exact: true })
  await expect(serviceLink).toHaveAttribute(
    'href',
    `/entities/${encodeURIComponent('SRV@1780656241.ooK3YN.assurance-service')}`,
  )
  const header = serviceLink.locator('xpath=ancestor::th')
  expect(await header.evaluate((element) => getComputedStyle(element).wordBreak)).toBe('normal')
})

test('GSN diagram renders and nodes are selectable in the generic viewer', async ({ page, request }, testInfo) => {
  const { problems } = watch(page)

  // Verify GSN is a generic diagram type (not assurance-only)
  const typesResp = await request.get('/api/diagram-types')
  expect(typesResp.ok()).toBeTruthy()
  const typeKeys = new Set((await typesResp.json() as Array<{ key: string }>).map((item) => item.key))
  expect(typeKeys.has('gsn')).toBe(true)

  // Find the stored GSN diagram
  const diagsResp = await request.get('/api/diagrams?diagram_type=gsn')
  expect(diagsResp.ok()).toBeTruthy()
  const { items } = await diagsResp.json() as DiagramList
  expect(items.length, 'T16 requires at least one stored GSN diagram').toBeGreaterThan(0)
  const gsn = items[0]

  // Verify the context endpoint surfaces diagram-owned nodes and edges
  const ctxResp = await request.get(`/api/diagrams/${encodeURIComponent(gsn.artifact_id)}/context`)
  expect(ctxResp.ok()).toBeTruthy()
  const ctx = await ctxResp.json() as DiagramContext
  expect(ctx.entities.length, 'GSN diagram must surface diagram-owned nodes as entities').toBeGreaterThan(0)

  // Navigate to the generic viewer
  await page.goto(`/diagrams/${encodeURIComponent(gsn.artifact_id)}`, { waitUntil: 'load' })
  await page.waitForTimeout(1000)
  await expectHealthyMain(page, problems)

  // Sidebar entity list must be populated
  const sidebar = page.locator('.ent-list .ent-item')
  await expect(sidebar.first()).toBeVisible()
  expect(await sidebar.count()).toBe(ctx.entities.length)

  // Click the first entity in the sidebar → detail panel must open
  await sidebar.first().click()
  const detailPanel = page.locator('.ent-det')
  await expect(detailPanel).toBeVisible()
  const detailName = detailPanel.locator('.det-name')
  await expect(detailName).toBeVisible()
  const nameText = await detailName.textContent()
  expect(nameText?.trim().length, 'Detail panel must show entity name').toBeGreaterThan(0)

  const screenshot = testInfo.outputPath('t16-gsn-node-selected.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T16 GSN node selection', { path: screenshot, contentType: 'image/png' })
})

test('C4 edit-view shows model-backed panel with derived entities', async ({ page, request }, testInfo) => {
  const { problems } = watch(page)

  // Find a model-backed C4 diagram (one with _scope_entity_id in diagram_entities)
  const diagsResp = await request.get('/api/diagrams?diagram_type=c4-container')
  expect(diagsResp.ok()).toBeTruthy()
  const { items } = await diagsResp.json() as DiagramList
  expect(items.length, 'T17 requires at least one stored C4 container diagram').toBeGreaterThan(0)
  const diagram = items[0]

  // Verify the context endpoint returns _scope_entity_id in diagram_entities
  const ctxResp = await request.get(`/api/diagrams/${encodeURIComponent(diagram.artifact_id)}/context`)
  expect(ctxResp.ok()).toBeTruthy()
  const ctx = await ctxResp.json() as DiagramContext
  const de = ctx.diagram.diagram_entities as Record<string, unknown> | null | undefined
  expect(de?._scope_entity_id, 'diagram_entities must carry _scope_entity_id for model-backed mode').toBeTruthy()
  expect(ctx.entities.length, 'Model-backed C4 must surface derived entities').toBeGreaterThan(0)

  // Navigate to the edit view
  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}/edit`, { waitUntil: 'load' })
  await page.waitForTimeout(2000)
  await expectHealthyMain(page, problems)

  // Model-backed panel must be visible with "Derived Entities" section
  const derivedSection = page.getByText('Derived Entities')
  await expect(derivedSection).toBeVisible()

  // Entity count badge must match the context response
  const countBadge = page.locator('.mbp-count').first()
  await expect(countBadge).toBeVisible()
  const countText = await countBadge.textContent()
  expect(Number(countText?.trim()), 'Derived entity count must be positive').toBeGreaterThan(0)

  const screenshot = testInfo.outputPath('t17-c4-edit-model-backed.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T17 C4 edit-view model-backed panel', { path: screenshot, contentType: 'image/png' })
})

test('C4 container create-view exposes shape selector for containers', async ({ page, request }, testInfo) => {
  test.setTimeout(60_000)
  const { problems } = watch(page)

  // Find a stored C4 container diagram to use its edit view (shape selector is in the edit UI)
  const diagsResp = await request.get('/api/diagrams?diagram_type=c4-container')
  expect(diagsResp.ok()).toBeTruthy()
  const { items } = await diagsResp.json() as DiagramList
  expect(items.length, 'T19 requires at least one stored C4 container diagram').toBeGreaterThan(0)
  const diagram = items[0]

  // Navigate to the edit view; switch to standalone mode (clear scope) to expose entity sections
  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}/edit`, { waitUntil: 'load' })
  await page.waitForTimeout(1500)

  // Assert the diagram-type ui-config exposes the shape enum property for containers
  const typeResp = await request.get('/api/diagram-types/c4-container/ui-config')
  expect(typeResp.ok()).toBeTruthy()
  const typeConfig = await typeResp.json() as {
    diagram_only_types?: Array<{ entity_type: string; properties?: Array<{ name: string; schema: unknown }> }>
  }
  const containerType = typeConfig.diagram_only_types?.find((t) => t.entity_type === 'container')
  expect(containerType, 'c4-container type must expose a container entity type').toBeTruthy()
  const shapeProp = containerType?.properties?.find((p) => p.name === 'shape')
  expect(shapeProp, 'container must have a "shape" property in the diagram type config').toBeTruthy()
  const shapeSchema = shapeProp?.schema as { type?: string; enum?: unknown[] } | undefined
  expect(shapeSchema?.type).toBe('string')
  expect(Array.isArray(shapeSchema?.enum), 'shape property must have enum values').toBe(true)
  expect((shapeSchema?.enum as unknown[]).length, 'shape enum must include at least Container, ContainerDb, ContainerQueue')
    .toBeGreaterThanOrEqual(3)

  await expectHealthyMain(page, problems)

  // Navigate to a C4 container diagram; verify SVG renders (shape inference works)
  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
  await page.waitForTimeout(1500)
  const svg = page.locator('.svg-wrap svg')
  await expect(svg).toBeVisible()
  await expectHealthyMain(page, problems)

  const screenshot = testInfo.outputPath('t19-c4-shape-selection.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T19 C4 shape selection', { path: screenshot, contentType: 'image/png' })
})

test('SVG node and edge click populates the detail sidebar (C4 + GSN)', async ({ page, request }, testInfo) => {
  test.setTimeout(120_000)
  const { problems } = watch(page)

  // ── C4: click derived entity node in rendered SVG ──────────────────────────
  const c4Resp = await request.get('/api/diagrams?diagram_type=c4-container')
  expect(c4Resp.ok()).toBeTruthy()
  const { items: c4Items } = await c4Resp.json() as DiagramList
  expect(c4Items.length, 'T18 requires at least one C4 container diagram').toBeGreaterThan(0)
  const c4Diagram = c4Items[0]

  await page.goto(`/diagrams/${encodeURIComponent(c4Diagram.artifact_id)}`, { waitUntil: 'load' })
  // Wait for SVG interactivity to attach (data-entity-id set on <g> elements), then
  // click a node and confirm the detail sidebar names a real entity.
  const c4NameText = await clickEntityNodeForDetail(page, 'C4')
  expect(c4NameText.length, 'C4 node click must populate name in detail panel').toBeGreaterThan(0)
  // A C4 node stands for a repository entity, so its name is a link to that entity's own page.
  await expect(page.locator('.ent-det .det-hdr a.det-name')).toBeVisible()

  // ── C4: click a connection/edge if one is present ─────────────────────────
  const c4Edge = page.locator('.svg-wrap [data-conn-id]').first()
  const c4EdgeCount = await c4Edge.count()
  if (c4EdgeCount > 0) {
    await c4Edge.click()
    await expect(page.locator('.conn-flow')).toBeVisible()
  }

  // ── GSN: click diagram-only node in rendered SVG ──────────────────────────
  const gsnResp = await request.get('/api/diagrams?diagram_type=gsn')
  expect(gsnResp.ok()).toBeTruthy()
  const { items: gsnItems } = await gsnResp.json() as DiagramList
  expect(gsnItems.length, 'T18 requires at least one GSN diagram').toBeGreaterThan(0)
  const gsnDiagram = gsnItems[0]

  await page.goto(`/diagrams/${encodeURIComponent(gsnDiagram.artifact_id)}`, { waitUntil: 'load' })
  const gsnNameText = await clickEntityNodeForDetail(page, 'GSN')
  expect(gsnNameText.length, 'GSN node click must populate name in detail panel').toBeGreaterThan(0)
  // A GSN node is diagram-only: it lives inside this diagram and has no standalone page, so the name
  // must be static. A link here would offer navigation to something that does not exist.
  await expect(page.locator('.ent-det .det-hdr .det-name--static')).toBeVisible()
  await expect(page.locator('.ent-det .det-hdr a.det-name')).toHaveCount(0)

  await expectHealthyMain(page, problems)
  const screenshot = testInfo.outputPath('t18-node-edge-selection.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T18 node/edge selection detail', { path: screenshot, contentType: 'image/png' })
})

test('C4 person labels render in system-context and container diagrams (T20)', async ({ page, request }, testInfo) => {
  test.setTimeout(120_000)
  const { problems } = watch(page)

  // ── system-context ────────────────────────────────────────────────────────
  const ctxResp = await request.get('/api/diagrams?diagram_type=c4-system-context')
  expect(ctxResp.ok()).toBeTruthy()
  const { items: ctxItems } = await ctxResp.json() as DiagramList
  expect(ctxItems.length, 'T20 requires at least one stored C4 system-context diagram').toBeGreaterThan(0)
  const ctxDiagram = ctxItems[0]

  await page.goto(`/diagrams/${encodeURIComponent(ctxDiagram.artifact_id)}`, { waitUntil: 'load' })
  const ctxSvg = page.locator('.svg-wrap svg')
  await expect(ctxSvg).toBeVisible({ timeout: 15_000 })
  const ctxSvgText = (await ctxSvg.textContent()) ?? ''

  // Fetch context to know which person labels to expect
  const ctxContextResp = await request.get(`/api/diagrams/${encodeURIComponent(ctxDiagram.artifact_id)}/context`)
  expect(ctxContextResp.ok()).toBeTruthy()
  const ctxContext = await ctxContextResp.json() as DiagramContext
  const ctxPersons = ctxContext.entities.filter((e) =>
    ['business-actor', 'business-role', 'role'].includes(e.artifact_type),
  )
  // At least one person label must appear in the SVG
  const ctxPersonsRendered = ctxPersons.filter((p) => ctxSvgText.includes(p.name))
  expect(
    ctxPersonsRendered.length,
    'System-context SVG must contain at least one person entity label',
  ).toBeGreaterThan(0)

  const ctxScreenshot = testInfo.outputPath('t20-c4-system-context-person-labels.png')
  await page.screenshot({ path: ctxScreenshot, fullPage: true })
  await testInfo.attach('T20 C4 system-context person labels', { path: ctxScreenshot, contentType: 'image/png' })

  // ── container ─────────────────────────────────────────────────────────────
  const ctnResp = await request.get('/api/diagrams?diagram_type=c4-container')
  expect(ctnResp.ok()).toBeTruthy()
  const { items: ctnItems } = await ctnResp.json() as DiagramList
  expect(ctnItems.length, 'T20 requires at least one stored C4 container diagram').toBeGreaterThan(0)
  const ctnDiagram = ctnItems[0]

  await page.goto(`/diagrams/${encodeURIComponent(ctnDiagram.artifact_id)}`, { waitUntil: 'load' })
  const ctnSvg = page.locator('.svg-wrap svg')
  await expect(ctnSvg).toBeVisible({ timeout: 15_000 })
  const ctnSvgText = (await ctnSvg.textContent()) ?? ''

  const ctnContextResp = await request.get(`/api/diagrams/${encodeURIComponent(ctnDiagram.artifact_id)}/context`)
  expect(ctnContextResp.ok()).toBeTruthy()
  const ctnContext = await ctnContextResp.json() as DiagramContext
  const ctnPersons = ctnContext.entities.filter((e) =>
    ['business-actor', 'business-role', 'role'].includes(e.artifact_type),
  )
  const ctnPersonsRendered = ctnPersons.filter((p) => ctnSvgText.includes(p.name))
  expect(
    ctnPersonsRendered.length,
    'Container diagram SVG must contain at least one person entity label',
  ).toBeGreaterThan(0)

  await expectHealthyMain(page, problems)
  const ctnScreenshot = testInfo.outputPath('t20-c4-container-person-labels.png')
  await page.screenshot({ path: ctnScreenshot, fullPage: true })
  await testInfo.attach('T20 C4 container person labels', { path: ctnScreenshot, contentType: 'image/png' })
})

test('C4 person→container edges anchor at nodes without gap (T21)', async ({ page, request }, testInfo) => {
  test.setTimeout(60_000)
  const { problems } = watch(page)

  // Use the stored container diagram (has person→container connections)
  const resp = await request.get('/api/diagrams?diagram_type=c4-container')
  expect(resp.ok()).toBeTruthy()
  const { items } = await resp.json() as DiagramList
  expect(items.length, 'T21 requires at least one stored C4 container diagram').toBeGreaterThan(0)
  const diagram = items[0]

  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
  const svg = page.locator('.svg-wrap svg')
  await expect(svg).toBeVisible({ timeout: 15_000 })

  // Verify the SVG contains connection lines: presence of 'uses' edge label and person + container labels
  const svgText = (await svg.textContent()) ?? ''
  const contextResp = await request.get(`/api/diagrams/${encodeURIComponent(diagram.artifact_id)}/context`)
  expect(contextResp.ok()).toBeTruthy()
  const context = await contextResp.json() as DiagramContext
  const persons = context.entities.filter((e) =>
    ['business-actor', 'business-role', 'role'].includes(e.artifact_type),
  )
  // At least one person label renders (anchored to an edge target)
  const renderedPersons = persons.filter((p) => svgText.includes(p.name))
  expect(
    renderedPersons.length,
    'Container diagram must render at least one person entity whose label appears in the SVG',
  ).toBeGreaterThan(0)

  // The SVG source must contain line/path elements (connection arrows)
  const svgSource = await page.evaluate(
    () => document.querySelector('.svg-wrap svg')?.outerHTML ?? '',
  )
  const hasConnections = svgSource.includes('<path') || svgSource.includes('<line')
  expect(hasConnections, 'SVG must contain path/line elements for person→container connections').toBe(true)

  await expectHealthyMain(page, problems)
  const screenshot = testInfo.outputPath('t21-c4-person-container-edge-anchoring.png')
  await page.screenshot({ path: screenshot, fullPage: true })
  await testInfo.attach('T21 C4 person→container edge anchoring', { path: screenshot, contentType: 'image/png' })
})

test('a cross-document link navigates in-app to the cited document', async ({ page }) => {
  // A same-directory citation (`[…](ADR@….md)`, no `docs/` segment) was left unrewritten, so the
  // browser resolved it against the current route and landed on `/documents/ADR@….md` — not a
  // route, so an error page. Nothing exercised a document-to-document hop, which is why the walk
  // below exists rather than only a unit test of the href mapping.
  const { problems } = watch(page)
  const source = 'ADR@1780761591._mseZr.adopt-archimate-next-ontology'
  await page.goto(`/documents/${encodeURIComponent(source)}`, { waitUntil: 'load' })
  await expectHealthyMain(page, problems)

  // Any in-app document link rendered from the body, not one specific target: the citations are
  // model content and may be re-authored, but that a citation is followed must keep holding.
  const citation = page.locator('#app > main a[href^="/documents/"]').first()
  await expect(citation).toBeVisible()
  const target = await citation.getAttribute('href')
  expect(target, 'a cited document must route to an id, never to a .md path').not.toMatch(/\.md($|[?#])/)

  await citation.click()
  await expect(page).toHaveURL(new RegExp(`${target?.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`))
  await expectHealthyMain(page, problems)
  // The destination is a real document view, not the SPA's not-found panel.
  await expect(page.locator('#app > main')).not.toContainText('Not found')
})
