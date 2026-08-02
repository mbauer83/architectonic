import { expect, test } from './coverage-fixture'

/**
 * The authoring path a human actually takes, end to end, in one flow.
 *
 * @verifies REQ@1712870400.NfAmrl
 *
 * The requirement asserts four things at once: browsing entities by domain, navigating connections,
 * viewing rendered diagrams, and creating entities with frontmatter auto-populated. The browser suite
 * already covered the first three, across several specs — and that is exactly why this requirement went
 * a release unverified. Marking any one of those specs would have claimed the conjunction on the
 * evidence of a quarter of it, and the claim being made is that these *compose* into a usable path: the
 * user who browses to a domain must be able to follow a connection out of what they find there, see a
 * diagram of it, and author into it, without ever leaving for a terminal.
 *
 * So this is one test rather than four, deliberately, and each step starts from where the previous one
 * left the browser instead of from a fresh `goto`. A four-test version would pass with the surfaces
 * mutually unreachable.
 *
 * **It creates nothing.** The fourth claim is that frontmatter arrives *auto-populated*, and the
 * dry-run preview is where the product shows that: it renders the whole file it would write, including
 * the fields the user never typed. Asserting against the preview is both the sharper evidence — the
 * created entity's own file would show the same fields with no way to tell which were typed — and the
 * only version that does not leave content in the live repository. A spec that authored here would
 * depend on cleanup never failing, which is how 247 lines once leaked into `viewpoints.yaml`.
 */

// The list views redirect a first-time visitor to group management, so seed the axis keys the way the
// route-walk does: this spec is about a returning user's path, not about onboarding.
test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    localStorage.setItem('arch_group_model-project', 'platform-core')
    // Empty string, not a collection slug: it is what `setGroup('')` stores when a user picks "All",
    // and it is the only seed that does not depend on which collection this repository files diagrams
    // in. Seeding a named one left the catalogue empty and the view redirected to group management,
    // where the same "All" control means something else — 30 seconds of clicking the wrong button.
    localStorage.setItem('arch_group_diagram-collection', '')
  })
})

test('browse by domain, follow a connection, see the diagram, author into it', async ({ page }) => {
  // ── 1. Browsing entities by domain ──────────────────────────────────────────────────────────────
  await page.goto('/entities', { waitUntil: 'load' })

  // The nav offers domains one of two ways: flat, when the active project restricts them to a single
  // framework, or behind a collapsed framework node when it does not. Both are the product's real
  // path — a spec that only knew the flat shape would pass on some repositories and not on this one.
  //
  // Waited for before either shape is *counted*: `count()` takes one sample and does not retry, so on
  // a frame where the group fetch has not landed both branches read zero, neither runs, and the spec
  // fails on the next line having never expanded anything. It passed alone and failed in the suite,
  // which is the signature of exactly this.
  await expect(page.locator('.tree-btn--framework, .tree-btn--domain').first()).toBeVisible()
  const framework = page.locator('.tree-btn--framework').first()
  if (await page.locator('.tree-btn--domain').count() === 0 && await framework.count() > 0) {
    await framework.click()
  }

  const domainButton = page.locator('.tree-btn--domain').first()
  await expect(domainButton, 'the group nav must offer at least one domain to browse').toBeVisible()
  const domainLabel = ((await domainButton.textContent()) ?? '').trim()
  await domainButton.click()

  // Through the URL, because that is what makes a browsed domain shareable and reloadable — a filter
  // held only in component state would satisfy the click and not the requirement.
  await expect(page).toHaveURL(/[?&]domain=/)
  const firstEntity = page.locator('main a[href^="/entities/"]').first()
  await expect(firstEntity, `browsing ${domainLabel} must yield entities`).toBeVisible()

  // ── 2. Navigating connections ───────────────────────────────────────────────────────────────────
  // Not necessarily the entity the domain listed first: the requirement is that connections are
  // navigable, and an entity with none cannot demonstrate that. So walk the listing for one that has
  // an outgoing connection, which is a property of the repository rather than of any fixed row.
  // `%40` — an *artifact id* in the path. `/entities/new` and `/entities/groups` are also
  // `a[href^="/entities/"]`, and following one of those looks exactly like an entity with no
  // connections: the create form has no connection panel to find.
  const entityHrefs = await page.locator('main a[href^="/entities/"]').evaluateAll(
    (anchors) => anchors
      .map((a) => a.getAttribute('href') ?? '')
      .filter((href) => href.includes('%40')),
  )
  expect(entityHrefs.length, 'the domain listing must offer an entity to start from').toBeGreaterThan(0)

  let connectionTarget: string | null = null
  for (const href of entityHrefs.slice(0, 8)) {
    await page.goto(href, { waitUntil: 'load' })
    // The connection panels arrive from their own fetch, and `count()` does not auto-retry — sampling
    // it on the first frame reported every entity as connectionless and failed the whole flow in under
    // two seconds. So wait for the panel, and treat its absence as "this entity is not the one" rather
    // than as a failure: an entity with no connections at all renders none, and the requirement is
    // about connections being navigable, not about every entity having one.
    const panelArrived = await page.locator('.conn-panel').first()
      .waitFor({ state: 'visible', timeout: 5000 }).then(() => true, () => false)
    if (!panelArrived) continue
    const outgoing = page.locator('.conn-item-wrap a[href^="/entities/"]').first()
    if (await outgoing.count() === 0) continue
    connectionTarget = ((await outgoing.textContent()) ?? '').trim()
    await outgoing.click()
    break
  }
  expect(connectionTarget, 'no entity in the browsed domain publishes a connection to follow').not.toBeNull()

  // Landing on the target's own detail surface is the navigation: a link that rendered but went
  // nowhere would have passed every assertion above it.
  await expect(page).toHaveURL(/\/entities\/.+/)
  await expect(page.locator('main')).toContainText(connectionTarget as string)

  // ── 3. Viewing a rendered diagram ───────────────────────────────────────────────────────────────
  await page.goto('/diagrams', { waitUntil: 'load' })
  // Waited for before it is read: `evaluateAll` takes one sample and does not retry, so collecting
  // straight after a navigation reads the frame before the catalogue's fetch resolves, and reports an
  // empty catalogue rather than a slow one.
  const diagramLinks = page.locator('.diagram-card a[href^="/diagrams/"]')
  await expect(diagramLinks.first(), 'the diagram catalogue must list something to open').toBeVisible()
  const diagramHrefs = await diagramLinks.evaluateAll(
    (anchors) => anchors.map((a) => a.getAttribute('href') ?? '').filter(Boolean),
  )
  expect(diagramHrefs.length).toBeGreaterThan(0)

  // Until one *renders*. The catalogue holds matrices as well, which are diagrams by kind and tables
  // by presentation, so the first row is not reliably a drawn one — and "viewing rendered diagrams" is
  // a claim about the drawn kind. `.svg-wrap svg` is what the renderer produced, so a diagram whose
  // render failed shows up here rather than as a page that merely loaded.
  let renderedDiagram = false
  for (const href of diagramHrefs.slice(0, 8)) {
    await page.goto(href, { waitUntil: 'load' })
    renderedDiagram = await page.locator('.svg-wrap svg')
      .waitFor({ state: 'visible', timeout: 5000 }).then(() => true, () => false)
    if (renderedDiagram) break
  }
  expect(renderedDiagram, 'no diagram in the catalogue rendered a drawing').toBe(true)

  // ── 4. Creating an entity, with frontmatter auto-populated ──────────────────────────────────────
  await page.goto('/entities/new', { waitUntil: 'load' })

  const typeSelect = page.locator('select').first()
  await expect(typeSelect).toBeVisible()
  await typeSelect.selectOption({ index: 1 })
  // By placeholder, not by label: the form's labels are not associated with their inputs (no
  // `for`/`id` pairing), so `getByLabel('Name')` matches nothing. Worth noting as an accessibility gap
  // in its own right — a screen reader has the same problem this locator did — but not this spec's to
  // fix, and using the placeholder does not paper over it.
  await page.getByPlaceholder('Human-readable name').fill('Exploration Path Probe')

  await page.getByRole('button', { name: 'Preview', exact: true }).click()

  const preview = page.locator('.preview-section')
  await expect(preview).toBeVisible()
  await expect(preview, 'the dry run must verify, or the form is offering to write a broken file')
    .toContainText('Verification passed.')

  // The claim, precisely: these fields are in the file the product would write and the user typed
  // none of them. `name` is excluded from this list on purpose — it is the one thing they did type.
  const previewed = (await preview.locator('pre').first().textContent()) ?? ''
  for (const field of ['artifact-id:', 'artifact-type:', 'version:', 'status:', 'last-updated:']) {
    expect(previewed, `frontmatter must arrive with ${field} filled in`).toContain(field)
  }
  // An id of the product's own convention rather than a placeholder the user is expected to replace.
  expect(previewed).toMatch(/artifact-id: [A-Z]{2,6}@\d+\.[A-Za-z0-9_-]+\.exploration-path-probe/)
})
