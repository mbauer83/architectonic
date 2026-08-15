import { test, expect } from './coverage-fixture'

/**
 * A picture of the graph as it stands, taken in a browser — which is the only place it can be
 * taken at all, and through the same menu a diagram offers — the affordance is shared, only what
 * downloading *means* differs. The markup builder is unit-tested; what those tests cannot show is that the thing
 * downloads, that the bytes are a usable file, and that the PNG path finds a canvas willing to
 * hand them back. `toBlob` throws on a tainted canvas, so a single remote reference anywhere in
 * the picture would break rasterising and nothing short of drawing it would say so.
 */

const ROOT = 'GOL@1780220699.FCfDuc.sustain-unity-of-effort-at-agentic-velocity'
const GRAPH = `/entities/${encodeURIComponent(ROOT)}/graph`

test('the SVG snapshot downloads and stands alone', async ({ page }) => {
  await page.goto(GRAPH)
  // The neighbourhood, not merely the first node to appear: a snapshot is of what is on screen, so
  // one taken mid-load faithfully captures a graph of one element. That is correct behaviour and a
  // useless assertion.
  await expect.poll(async () => page.locator('svg g.graph-node').count()).toBeGreaterThan(10)

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    (async () => {
      await page.getByRole('button', { name: 'Download' }).click()
      await page.getByRole('button', { name: 'SVG', exact: true }).click()
    })(),
  ])

  expect(download.suggestedFilename()).toMatch(/\.svg$/)
  const stream = await download.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  const markup = Buffer.concat(chunks).toString('utf8')

  // Standalone: a namespace, an absolute size, a font of its own, and a ground to draw on.
  expect(markup).toContain('http://www.w3.org/2000/svg')
  expect(markup).toMatch(/<svg[^>]*width="\d+"/)
  expect(markup).toMatch(/font-family=/)
  // And the drawing: a node's title carries its name, which is how the picture is readable at all.
  expect(markup).toContain('Sustain Unity of Effort')
})

test('the PNG snapshot downloads as a raster', async ({ page }) => {
  await page.goto(GRAPH)
  await expect.poll(async () => page.locator('svg g.graph-node').count()).toBeGreaterThan(10)

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    (async () => {
      await page.getByRole('button', { name: 'Download' }).click()
      await page.getByRole('button', { name: 'PNG', exact: true }).click()
    })(),
  ])

  expect(download.suggestedFilename()).toMatch(/\.png$/)
  const stream = await download.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  const bytes = Buffer.concat(chunks)

  // The PNG signature, and enough of them to be a picture rather than an empty canvas.
  expect(bytes.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
  expect(bytes.length).toBeGreaterThan(5000)
})
