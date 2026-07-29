/**
 * Force mode has to move visibly, and then stop.
 *
 * Expanding a node used to make the whole graph disappear for a moment and come back already
 * rearranged. Two mechanisms combined to do it: the canvas hid itself until a fit had landed
 * for the *current* population, and every population change invalidated that fit; meanwhile
 * the simulation was driven to rest synchronously, so the entire rearrangement happened
 * between two paints. The reader had no way to tell which nodes were new, or where the ones
 * they were watching had gone.
 *
 * The synchronous settle was not gratuitous — it was bought to stop the graph drifting under
 * the pointer, which the loop it replaced could do indefinitely, because "nothing is moving
 * much right now" is not a proof that a force simulation will ever stop. So animating it back
 * is only correct alongside a termination guarantee, and both are asserted here:
 *
 *   1. the canvas stays painted across an expansion,
 *   2. the motion is a run of intermediate positions rather than a jump, and
 *   3. it reaches a fixed point and stays on it.
 *
 * The cooling schedule that provides (3) is unit-tested in `forceSimulation.test.ts`; this
 * holds the property end to end, through the real canvas, where a stray watcher or a re-fit
 * could still restart the graph after it had come to rest.
 */
import { expect, test, type Page } from '@playwright/test'

const ANCHOR = 'OUT@1780655839.Vhhne7.assurance-analysis-surfaces-modeling-gaps'

/** Every node's transform, joined — the whole arrangement, not one node's corner of it. */
const arrangement = async (page: Page): Promise<string> =>
  page.locator('.graph-node').evaluateAll(
    (nodes) => nodes.map((n) => n.getAttribute('transform') ?? '').join('|'),
  )

/**
 * Wait until the graph stops moving.
 *
 * Polling for two identical readings of *every* node, as in the cluster suite: a fixed pause
 * races the animation, and the anchor alone is nearly stationary, so watching it reports "at
 * rest" while the rest of the graph is still easing into place.
 *
 * `networkidle` first, and this is not incidental. Adding a hop puts its nodes on the canvas
 * immediately but only lays them out once every new node's domain has been fetched — cluster
 * mode groups by domain, so laying out earlier would file them all under "unknown". In that
 * gap the nodes sit motionless at their seeded positions, which reads identically to "at
 * rest" and would have this helper report the graph settled before it had begun to move.
 */
const settled = async (page: Page): Promise<void> => {
  await page.waitForLoadState('networkidle')
  let previous = ''
  await expect.poll(async () => {
    const current = await arrangement(page)
    const stable = current !== '' && current === previous
    previous = current
    return stable
  }, { timeout: 20_000, intervals: [120] }).toBe(true)
}

/** Open the graph in force mode — the default — and let the initial layout come to rest. */
const openForce = async (page: Page): Promise<void> => {
  await page.goto(`/graph?id=${encodeURIComponent(ANCHOR)}`, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: 'Force', exact: true }))
    .toHaveClass(/spacing-btn--active/)
  // The initial load legitimately withholds the first paint until a fit has landed, so wait
  // for the graph to be on screen before any test starts asserting about what it does there.
  await expect(page.locator('.graph-svg')).toBeVisible({ timeout: 20_000 })
  await settled(page)
}

const expandFirst = async (page: Page): Promise<void> => {
  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
}

test('the canvas stays visible while an expansion plays out', async ({ page }) => {
  await openForce(page)

  // Sample every frame: the blink lasted one synchronous settle, so a poll would step over it.
  const hidden: number[] = []
  await page.exposeFunction('__vis', (visible: boolean, nodes: number) => {
    if (!visible && nodes > 0) hidden.push(nodes)
  })
  await page.evaluate(() => {
    const tick = (): void => {
      const svg = document.querySelector('.graph-svg')
      if (svg !== null) {
        void (window as unknown as { __vis: (v: boolean, n: number) => void }).__vis(
          getComputedStyle(svg).visibility === 'visible',
          document.querySelectorAll('.graph-node').length,
        )
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  await expandFirst(page)
  await settled(page)

  expect(hidden, `the canvas was hidden on ${hidden.length} frame(s) during expansion`).toEqual([])
})

test('expanding animates rather than teleporting', async ({ page }) => {
  await openForce(page)

  const frames: string[] = []
  await page.exposeFunction('__arr', (value: string) => {
    if (frames[frames.length - 1] !== value) frames.push(value)
  })
  await page.evaluate(() => {
    const tick = (): void => {
      const nodes = [...document.querySelectorAll('.graph-node')]
      if (nodes.length > 0) {
        void (window as unknown as { __arr: (v: string) => void }).__arr(
          nodes.map((n) => n.getAttribute('transform') ?? '').join('|'),
        )
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  await expandFirst(page)
  await settled(page)

  // A rearrangement applied between two paints yields two distinct arrangements: before and
  // after. Cooling to rest across real frames yields a run of intermediate ones.
  expect(frames.length, `arrangements seen: ${frames.length}`).toBeGreaterThan(4)
})

test('the graph reaches a fixed point and stays on it', async ({ page }) => {
  await openForce(page)
  await expandFirst(page)
  await settled(page)

  // The anti-drift assertion, and the reason animating is safe at all. A simulation left
  // running without a cooling schedule can trade energy around a balanced graph forever, and
  // the visible symptom is nodes sliding out from under the pointer well after the expansion
  // appeared to finish. Sampling a full second after rest is what catches that.
  const atRest = await arrangement(page)
  await page.waitForTimeout(1000)

  expect(await arrangement(page)).toBe(atRest)
})

test('a second expansion still animates and still comes to rest', async ({ page }) => {
  // Once, the paint gate happened to be satisfied for the first expansion and not the second.
  // Walking two hops is the cheapest way to keep that class of asymmetry out.
  await openForce(page)
  await expandFirst(page)
  await settled(page)

  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).nth(1).dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await settled(page)

  const atRest = await arrangement(page)
  await page.waitForTimeout(800)

  expect(await arrangement(page)).toBe(atRest)
})

test('radial rings the walk around the entity it opened on', async ({ page }) => {
  // Radial was offered only for anchored viewpoint executions, on the grounds that it needs an
  // anchor and free exploration had none. It has one — the entity the route opened on — and
  // the parentage the walk records gives every node its hop distance from it.
  await openForce(page)
  await expandFirst(page)
  await settled(page)

  await page.getByRole('button', { name: 'Radial', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Radial', exact: true }))
    .toHaveClass(/spacing-btn--active/)
  await settled(page)

  const rings = await page.locator('.graph-node').evaluateAll((nodes) => {
    const pts = nodes.map((n) => {
      const m = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(n.getAttribute('transform') ?? '')
      return { x: Number(m?.[1] ?? 0), y: Number(m?.[2] ?? 0) }
    })
    // The anchor sits at the centre of the rings, so the centroid is a good enough origin to
    // bucket radii around without reaching into the app's own state.
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length
    return [...new Set(pts.map((p) => Math.round(Math.hypot(p.x - cx, p.y - cy) / 40)))].length
  })

  // More than one distinct radius: nodes lie on rings, not scattered or piled at one distance.
  expect(rings).toBeGreaterThan(1)
})

test('new neighbours arrive coloured, never grey-then-recoloured', async ({ page }) => {
  /*
   * Expansion used to publish its nodes before resolving them: they appeared grey and
   * unlabelled at their seeded scatter positions, sat there for the length of a fetch per
   * node, and then snapped elsewhere once the domains arrived and the layout could run. Three
   * visible states for one action, two of which nobody asked to see.
   *
   * `#6b7280` is the fill a node gets when its domain is unknown — so counting nodes painted
   * in it counts exactly the unresolved ones, without reaching into the app's state.
   */
  await openForce(page)

  const greyFrames: number[] = []
  await page.exposeFunction('__grey', (count: number) => {
    if (count > 0) greyFrames.push(count)
  })
  await page.evaluate(() => {
    const tick = (): void => {
      const grey = [...document.querySelectorAll('.graph-node polygon')]
        .filter((p) => p.getAttribute('fill') === '#6b7280').length
      void (window as unknown as { __grey: (n: number) => void }).__grey(grey)
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  await expandFirst(page)
  await settled(page)

  expect(greyFrames.length, `unresolved nodes were painted on ${greyFrames.length} frame(s)`)
    .toBe(0)
})
