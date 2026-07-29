/**
 * Cluster mode has to be usable, not just correct on paper.
 *
 * Three defects, all of them visible on the first expansion and none of them caught by the
 * layout's own unit tests, because each lived in the gap between two components that each
 * looked right alone.
 *
 * 1. **Overlap.** The layout sized grid cells from its own guess at a node's width
 *    (`44 + label.length * 1.5`) while the renderer drew the *wrapped* label, and it used a
 *    constant 90px row height against nodes that draw 83px tall — 99px for an anchor. Two
 *    descriptions of one geometry, and the grid was built from the wrong one. A side group
 *    also hung below its band because band height was measured from the stacked boxes only.
 * 2. **Two clicks to expand.** Every mousedown entered drag state, so the first half of a
 *    double-click pinned the node, nudged it, and fired a layout tick on release that moved
 *    the graph out from under the pointer.
 * 3. **No animation.** Cluster layouts assigned final positions outright, so the graph
 *    teleported and the reader lost track of what moved where.
 */
import { expect, test, type Page } from '@playwright/test'

const ANCHOR = 'OUT@1780655839.Vhhne7.assurance-analysis-surfaces-modeling-gaps'

/**
 * Wait until the graph stops moving.
 *
 * A fixed pause would be a race against the relayout tween: it runs for a set duration but
 * starts whenever the layout does, so under parallel load the sleep expires mid-animation and
 * the test samples a position that is still on its way somewhere. Polling for two identical
 * readings waits for the thing that actually matters — that the graph has come to rest.
 */
const settled = async (page: Page): Promise<void> => {
  let previous = ''
  await expect.poll(async () => {
    // Every node, not just the first. The anchor is centred and often barely moves, so
    // watching it alone reports "at rest" while the rest of the graph is still easing into
    // place — and a mid-animation sample looks exactly like a broken layout.
    const current = (await page.locator('.graph-node').evaluateAll(
      (nodes) => nodes.map((n) => n.getAttribute('transform') ?? '').join('|'),
    ))
    const stable = current !== '' && current === previous
    previous = current
    return stable
  }, { timeout: 20_000, intervals: [120] }).toBe(true)
}

const openCluster = async (page: Page): Promise<void> => {
  await page.goto(`/graph?id=${encodeURIComponent(ANCHOR)}`, { waitUntil: 'load' })
  await expect(page.locator('.graph-node').first()).toBeAttached({ timeout: 20_000 })
  await page.getByRole('button', { name: 'Cluster', exact: true }).click()
  await settled(page)
}

/** Pairs whose drawn boxes intersect by more than a couple of pixels on both axes. */
const overlappingPairs = async (page: Page): Promise<string[]> =>
  page.evaluate(() => {
    const boxes = [...document.querySelectorAll('.graph-node')].map((node) => {
      const bounds = (node as SVGGElement).getBBox()
      const shift = /translate\(([-\d.]+),\s*([-\d.]+)\)/.exec(node.getAttribute('transform') ?? '')
      return {
        label: (node.querySelector('text')?.textContent ?? '').trim().slice(0, 24),
        x: bounds.x + Number(shift?.[1] ?? 0), y: bounds.y + Number(shift?.[2] ?? 0),
        w: bounds.width, h: bounds.height,
      }
    })
    const clashes: string[] = []
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i]!, b = boxes[j]!
        const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
        const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
        if (overlapX > 2 && overlapY > 2) {
          clashes.push(`${a.label} ⟷ ${b.label} (${Math.round(overlapX)}×${Math.round(overlapY)}px)`)
        }
      }
    }
    return clashes
  })

const expandOne = async (page: Page, index = 0): Promise<number> => {
  const nodes = page.locator('.graph-node')
  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).nth(index).dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await settled(page)
  return before
}

test('nodes never overlap, however far the graph is walked', async ({ page }) => {
  await openCluster(page)
  expect(await overlappingPairs(page), 'overlaps before any expansion').toEqual([])

  for (let round = 0; round < 3; round++) {
    await expandOne(page, round)
    expect(await overlappingPairs(page), `overlaps after ${round + 1} expansion(s)`).toEqual([])
  }

  expect(await page.locator('.graph-node').count()).toBeGreaterThan(10)
})

test('one double-click expands — a press is not a drag', async ({ page }) => {
  await openCluster(page)
  const nodes = page.locator('.graph-node')
  const target = nodes.filter({ has: page.locator('.expand-badge') }).first()
  const before = await nodes.count()

  // Real pointer input, not a synthetic dblclick event: the defect was in how the press was
  // handled, so dispatching the composed event directly would have stepped right over it.
  const box = (await target.boundingBox())!
  await page.mouse.dblclick(box.x + box.width / 2, box.y + 12)

  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
})

test('a click leaves the node where it was', async ({ page }) => {
  await openCluster(page)
  const target = page.locator('.graph-node').first()
  const positionOf = async (): Promise<string | null> => target.getAttribute('transform')
  const before = await positionOf()

  const box = (await target.boundingBox())!
  // A hand is never perfectly still between press and release; two pixels must not move it.
  await page.mouse.move(box.x + box.width / 2, box.y + 12)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 2, box.y + 13)
  await page.mouse.up()
  await settled(page)

  expect(await positionOf()).toBe(before)
})

test('a deliberate drag still moves the node', async ({ page }) => {
  await openCluster(page)
  const target = page.locator('.graph-node').first()
  const before = await target.getAttribute('transform')

  const box = (await target.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 12)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + 52, { steps: 6 })
  await page.mouse.up()

  expect(await target.getAttribute('transform')).not.toBe(before)
})

test('expanding animates rather than teleporting', async ({ page }) => {
  await openCluster(page)
  const nodes = page.locator('.graph-node')

  const frames: string[] = []
  await page.exposeFunction('__pos', (value: string) => {
    if (frames[frames.length - 1] !== value) frames.push(value)
  })
  // Every node, for the same reason `settled()` above polls every node: the first in document
  // order is usually the anchor, which cluster mode centres — so it can sit still through an
  // entire animation and report a teleport that never happened. This watched only that node,
  // and started failing the moment expansion stopped painting an intermediate scattered state
  // before laying out (nodes are now resolved before they are published, so there is nothing
  // half-finished to paint). The graph was animating throughout; the probe could not see it.
  await page.evaluate(() => {
    const tick = (): void => {
      const all = [...document.querySelectorAll('.graph-node')]
      if (all.length > 0) {
        void (window as unknown as { __pos: (v: string) => void }).__pos(
          all.map((n) => n.getAttribute('transform') ?? '').join('|'),
        )
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })

  const before = await nodes.count()
  await nodes.filter({ has: page.locator('.expand-badge') }).first().dispatchEvent('dblclick')
  await expect.poll(async () => nodes.count(), { timeout: 20_000 }).toBeGreaterThan(before)
  await page.waitForTimeout(700)

  // A teleport produces exactly two distinct arrangements: before and after. Easing produces a
  // run of intermediate ones.
  expect(frames.length, `arrangements seen: ${frames.length}`).toBeGreaterThan(4)
})
