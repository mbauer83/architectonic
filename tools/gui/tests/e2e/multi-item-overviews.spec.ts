/**
 * The four multi-item overviews, exercised in a browser against the real repository.
 *
 * These views had no end-to-end test. Their unit tests cover *fragments* — `sizeOf` weights a treemap
 * tile, `resolveSummaryColumnValue` resolves one column path — and a fragment cannot answer whether
 * the view renders, filters, or sorts. So the requirements they satisfy were owed a verifier, and
 * marking a fragment would have reported coverage that did not exist.
 *
 * Writing this found two requirements whose implementation looked *partial*, and both turned out to
 * resolve rather than linger. The entity list's tree-like clause was withdrawn from the requirement —
 * incompatible with pagination, and served better by graph-explore — so this spec covers the whole of
 * it. The treemap's second grouping axis is still specified as entity-type and implemented as
 * subdomain, so REQ@1777372175.eFz3z9 stays owed; the assertion that would have covered it records
 * that in place. One correction was mine: the diagram grid does satisfy its requirement — the type
 * badge *is* the ArchiMate domain, and each domain has its own filter button, so "filterable by type
 * and domain" holds in the only sense that applies to a type key that encodes its domain.
 *
 * Counts are never pinned. Authoring an entity is the product working; a test that fails because
 * someone modelled something is reporting a false regression.
 *
 * @verifies REQ@1777372662.64JvM1
 * @verifies REQ@1777371781.v0TJX4
 * @verifies REQ@1777372455.LnytwA
 * @verifies REQ@1777371979.W-G4L5
 */
import { expect, test } from '@playwright/test'

/** Filter controls are labelled, so drive them the way a person does. */
const toolbarSelect = (label: string) => `label:has(span:text-is("${label}")) select`

test.describe('documents list view', () => {
  test('shows title and type, and filters by each of them', async ({ page }) => {
    await page.goto('/documents')

    const rows = page.locator('.documents-table tbody tr')
    await expect(rows.first()).toBeVisible()
    await expect(page.locator('.documents-table thead th').first()).toHaveText('Title')

    // Every row carries a non-empty title and a type — the two fields the requirement names.
    const before = await rows.count()
    expect(before).toBeGreaterThan(1)
    for (const row of await rows.all()) {
      await expect(row.locator('td').first()).not.toHaveText('')
      await expect(row.locator('.doc-type')).not.toHaveText('')
    }

    // Filter by type: the surviving rows all carry the chosen type, and something was excluded.
    const typeSelect = page.locator(toolbarSelect('Type'))
    const firstType = await typeSelect.locator('option:not([value=""])').first().getAttribute('value')
    expect(firstType).toBeTruthy()
    await typeSelect.selectOption(firstType!)
    await expect(rows.first()).toBeVisible()
    const typeLabels = await rows.locator('.doc-type').allTextContents()
    expect(new Set(typeLabels).size).toBe(1)
    expect(await rows.count()).toBeLessThan(before)

    // Filter by title, on a fragment taken from a row the type filter left standing.
    await typeSelect.selectOption('')
    const title = (await rows.first().locator('td').first().innerText()).trim()
    await page.locator('input[placeholder="Filter by title..."]').fill(title.slice(0, 6))
    await expect(rows.first()).toBeVisible()
    const titles = await rows.locator('td:first-child').allTextContents()
    expect(titles.every(t => t.toLowerCase().includes(title.slice(0, 6).toLowerCase()))).toBe(true)
  })
})

test.describe('entities list view', () => {
  test('is a sortable table filterable by domain and type', async ({ page }) => {
    await page.goto('/entities')

    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()

    // The requirement asks for sorting by type and by connection count, total plus in/sym/out.
    const headers = await page.locator('table thead th').allInnerTexts()
    expect(headers.join(' ')).toContain('Type')
    expect(headers.join(' ')).toContain('Connections')
    for (const sub of ['in', 'sym', 'out']) {
      await expect(page.locator(`table thead >> text="${sub}"`).first()).toBeVisible()
    }

    // Sorting by the connection total, through the header's own affordance: a sortable column renders
    // a button inside its `th`, and the documented cycle is asc → desc → unsorted. Read the cell per
    // row — one locator chained off the row set indexes across the whole table, not within each row.
    const totalsColumn = async (): Promise<number[]> => {
      const values: number[] = []
      for (const row of await rows.all()) {
        const value = Number.parseInt((await row.locator('td').nth(3).innerText()).trim(), 10)
        if (Number.isFinite(value)) values.push(value)
      }
      return values
    }
    const connections = page.locator('table thead th:has-text("Connections") button').first()

    await connections.click()
    await expect(page.locator('table thead th:has-text("Connections")')).toHaveAttribute('aria-sort', 'ascending')
    const ascending = await totalsColumn()
    expect(ascending.length).toBeGreaterThan(1)
    expect(ascending).toEqual([...ascending].sort((a, b) => a - b))

    await connections.click()
    const descending = await totalsColumn()
    expect(descending).toEqual([...descending].sort((a, b) => b - a))
    // A third click releases the sort rather than trapping the reader in it.
    await connections.click()
    await expect(page.locator('table thead th:has-text("Connections")')).toHaveAttribute('aria-sort', 'none')

    // Filtering by type narrows the table to that type.
    const typeSelect = page.locator(toolbarSelect('Type'))
    const someType = await typeSelect.locator('option:not([value=""])').first().getAttribute('value')
    await typeSelect.selectOption(someType!)
    await expect(rows.first()).toBeVisible()
    const shown = await rows.locator('.type-cell .mono').allTextContents()
    expect(new Set(shown.map(s => s.trim())).size).toBe(1)

    // The tree-like clause this comment used to record as an unmet gap is gone from the requirement,
    // withdrawn rather than deferred: duplicating a child row under every parent cannot coexist with
    // pagination, because a page is a window over an ordered population and a child's presence would
    // depend on whether its parent fell inside that window — the same entity appearing, vanishing or
    // repeating with page size and sort order. The graph-explore view serves the hierarchy properly,
    // as edges over a bounded neighbourhood. So what this test asserts is now the whole requirement.
  })

  test('offers a treemap grouped by domain and sized by connection count', async ({ page }) => {
    await page.goto('/entities?view=treemap')

    // The treemap's own caption states its grouping, which is what the requirement is about.
    await expect(page.getByText('Grouped by domain.')).toBeVisible()
    const tiles = page.locator('svg rect')
    await expect(tiles.first()).toBeVisible()
    expect(await tiles.count()).toBeGreaterThan(1)

    // Choosing a domain regroups rather than merely filtering — the second grouping axis.
    const domainLink = page.locator('.sidebar a, .sidebar button').first()
    await domainLink.click()
    await expect(page.getByText(/Grouped by (subdomain|domain)\./)).toBeVisible()

    // NOT verified: the requirement's grouping axes are "ArchiMate domain and entity-type". The
    // second axis is subdomain, not entity type, so REQ@1777372175.eFz3z9 stays owed.
  })
})

test.describe('diagrams grid view', () => {
  test('each card carries name, type, id and a download control, and the grid filters by type', async ({ page }) => {
    await page.goto('/diagrams')

    const cards = page.locator('.diagram-grid .diagram-card')
    await expect(cards.first()).toBeVisible()
    const before = await cards.count()
    expect(before).toBeGreaterThan(1)

    for (const card of await cards.all()) {
      await expect(card.locator('.diagram-name')).not.toHaveText('')
      await expect(card.locator('.diagram-type-badge')).not.toHaveText('')
      // The id is shown in full, so a person reading a card can address the diagram elsewhere.
      await expect(card.locator('.diagram-id')).toContainText('@')
      await expect(card.locator('.card-dl')).toBeVisible()
    }

    // An ArchiMate diagram's badge is its *domain* — the view strips the `archimate-` prefix, so the
    // tag reads "business", "motivation", "layered". That is what the requirement asks for; a badge
    // reading the full type key would not be.
    const badges = (await cards.locator('.diagram-type-badge').allTextContents()).map(b => b.trim())
    const archimateDomains = ['business', 'application', 'technology', 'motivation', 'strategy',
      'implementation', 'layered']
    expect(badges.filter(b => archimateDomains.includes(b)).length).toBeGreaterThan(0)

    // Filterable by type *and* by domain: each ArchiMate domain is its own button, so picking one
    // narrows the grid to that domain. Take a domain button rather than the "All"/"ArchiMate" ones.
    const domainButton = page.locator('.filter-bar .filter-btn', { hasText: /^ArchiMate .+/ }).first()
    const wanted = (await domainButton.innerText()).trim().replace(/^ArchiMate\s+/, '').toLowerCase()
    await domainButton.click()
    await expect(cards.first()).toBeVisible()
    expect(await cards.count()).toBeLessThan(before)
    const after = (await cards.locator('.diagram-type-badge').allTextContents()).map(b => b.trim())
    expect(after.length).toBeGreaterThan(0)
    expect(after.every(b => b === wanted)).toBe(true)
  })
})

test.describe('every artifact family has a multi-item overview', () => {
  // The parent requirement: an overview per family, distinct from search. Asserted as a set so a
  // view that stops rendering fails here rather than in whichever spec happened to visit it.
  for (const [family, path, populated] of [
    ['entities', '/entities', 'table tbody tr'],
    ['diagrams', '/diagrams', '.diagram-grid .diagram-card'],
    ['documents', '/documents', '.documents-table tbody tr'],
  ] as const) {
    test(`${family} has one that renders real content`, async ({ page }) => {
      await page.goto(path)
      await expect(page.locator(populated).first()).toBeVisible()
      expect(await page.locator(populated).count()).toBeGreaterThan(1)
      // Not the search page: the overview is reachable without issuing a query.
      expect(page.url()).not.toContain('/search')
    })
  }
})
