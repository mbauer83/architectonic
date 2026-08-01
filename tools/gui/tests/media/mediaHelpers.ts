import { expect, type APIRequestContext, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export type Problem = { kind: string; detail: string }
export type DiagramSummary = { artifact_id: string; name: string; diagram_type: string }
type DiagramList = { items: DiagramSummary[] }

export interface CaptureProvenance {
  test_name: string
  artifact_ids: readonly string[]
  viewpoint_slug?: string
  parameters?: Readonly<Record<string, string | readonly string[]>>
  synthetic_augmentation: boolean
}

interface ManifestEntry extends Omit<CaptureProvenance, 'viewpoint_slug' | 'parameters'> {
  viewpoint_slug: string | null
  parameters: Readonly<Record<string, string | readonly string[]>>
  viewport: { width: 1440; height: 900; device_scale_factor: 2 }
  capture_tool_version: string
  output_path: string
  sha256: string
}

const here = path.dirname(fileURLToPath(import.meta.url))
const mediaDir = path.resolve(here, '../../../../docs/media')
const manifestPath = path.join(mediaDir, 'manifest.json')
const playwrightMetadata = JSON.parse(fs.readFileSync(
  path.resolve(here, '../../node_modules/@playwright/test/package.json'), 'utf8',
)) as { version: string }

export function mediaPath(fileName: string): string {
  fs.mkdirSync(mediaDir, { recursive: true })
  return path.join(mediaDir, fileName)
}

export function resetManifest(): void {
  fs.writeFileSync(manifestPath, '[]\n')
}

function record(fileName: string, provenance: CaptureProvenance): void {
  const bytes = fs.readFileSync(mediaPath(fileName))
  const current = fs.existsSync(manifestPath)
    ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as ManifestEntry[]
    : []
  const entry: ManifestEntry = {
    ...provenance,
    viewpoint_slug: provenance.viewpoint_slug ?? null,
    parameters: provenance.parameters ?? {},
    viewport: { width: 1440, height: 900, device_scale_factor: 2 },
    capture_tool_version: `Playwright ${playwrightMetadata.version}`,
    output_path: `docs/media/${fileName}`,
    sha256: createHash('sha256').update(bytes).digest('hex'),
  }
  const merged = [...current.filter((item) => item.output_path !== entry.output_path), entry]
    .sort((left, right) => left.output_path.localeCompare(right.output_path))
  fs.writeFileSync(manifestPath, `${JSON.stringify(merged, null, 2)}\n`)
}

export function watch(page: Page): Problem[] {
  const problems: Problem[] = []
  page.on('pageerror', (err) => problems.push({ kind: 'pageerror', detail: String(err) }))
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    if (/Failed to load resource.*status of 423/.test(msg.text()) && msg.location().url.includes('/api/assurance')) return
    problems.push({ kind: 'console.error', detail: msg.text() })
  })
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 500) {
      problems.push({ kind: `http ${response.status()}`, detail: response.url() })
    }
  })
  return problems
}

/**
 * Scroll so `selector` sits `offset` px below the top of the viewport, and wait until it has settled.
 *
 * Replaces `scrollIntoView()` followed by a relative `scrollBy()`. That pairing is timing-sensitive:
 * the two steps read layout at different moments, so a row still settling above the target shifted the
 * final position by a pixel or two — enough for a figure to alternate between two byte values across
 * runs while looking identical. Here the target is computed once from the document offset, applied
 * absolutely, and then confirmed stable across two frames before anything is captured.
 */
export async function scrollToStable(page: Page, selector: string, offset: number): Promise<void> {
  await page.locator(selector).evaluate((element, top) => {
    const target = element.getBoundingClientRect().top + window.scrollY - top
    window.scrollTo({ top: Math.max(0, Math.round(target)), behavior: 'instant' })
  }, offset)
  await page.waitForFunction(() => {
    const seen = (window as unknown as { __lastScrollY?: number }).__lastScrollY
    const now = Math.round(window.scrollY)
    ;(window as unknown as { __lastScrollY?: number }).__lastScrollY = now
    return seen === now
  }, undefined, { timeout: 10_000 })
}

/**
 * Every "Loading…" / "Loading <something>…" placeholder the views render while fetching.
 *
 * Views paint their shell immediately and fill it when data arrives, so `main` being visible
 * says nothing about whether there is anything in it. Waiting on a fixed delay instead is a
 * coin flip, and losing it ships a figure of the word "Loading…" — which is exactly what
 * happened to the entity-catalog screenshot, while a second figure of the very same route
 * won the race and looked fine.
 */
const LOADING_PLACEHOLDER = /^\s*Loading\b.*(…|\.\.\.)\s*$/

export async function capture(
  page: Page,
  fileName: string,
  provenance: CaptureProvenance,
): Promise<void> {
  await expect(page.locator('#app > main')).toBeVisible()
  await expect(
    page.getByText(LOADING_PLACEHOLDER),
    `${fileName} was still loading when the shot was taken`,
  ).toHaveCount(0, { timeout: 20_000 })
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
  await page.screenshot({ path: mediaPath(fileName), animations: 'disabled' })
  record(fileName, provenance)
}

export async function gotoAndCapture(
  page: Page,
  route: string,
  fileName: string,
  provenance: CaptureProvenance,
): Promise<void> {
  const problems = watch(page)
  await page.goto(route, { waitUntil: 'load' })
  await capture(page, fileName, provenance)
  expect(problems, `runtime problems while capturing ${fileName}`).toEqual([])
}

/**
 * Capture an animated figure as a sequence of still beats and assemble them into a GIF.
 *
 * Recording video and transcoding would capture the force simulation's motion, which is not
 * what the figure is for — expansion snaps the layout to rest deliberately, so the story is
 * the sequence of states, not the transition between them. Stills also keep every label
 * legible at the widths documentation renders at, which a compressed video does not.
 *
 * Frames are scaled down on assembly: the shots are taken at device-scale 2 for sharpness and
 * a GIF at that size would be several megabytes.
 */
export async function captureAnimation(
  page: Page,
  fileName: string,
  provenance: CaptureProvenance,
  beats: ReadonlyArray<{ name: string; act: () => Promise<void> }>,
  options: { delayCs?: number; widthPx?: number } = {},
): Promise<void> {
  const { delayCs = 180, widthPx = 1100 } = options
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'arch-gif-'))
  try {
    const frames: string[] = []
    for (const [index, beat] of beats.entries()) {
      await beat.act()
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(250)
      const frame = path.join(scratch, `${String(index).padStart(3, '0')}-${beat.name}.png`)
      await page.screenshot({ path: frame, animations: 'disabled' })
      frames.push(frame)
    }
    // ImageMagick, not ffmpeg: only `convert` is a documented prerequisite of this repo's
    // media workflow, and a still-sequence GIF is exactly what it is good at.
    execFileSync('convert', [
      '-delay', String(delayCs), '-loop', '0',
      ...frames, '-resize', `${widthPx}x`, '-layers', 'Optimize',
      mediaPath(fileName),
    ], { stdio: 'pipe' })
    record(fileName, provenance)
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true })
  }
}

export async function diagramById(
  request: APIRequestContext,
  artifactId: string,
): Promise<DiagramSummary> {
  const response = await request.get('/api/diagrams')
  expect(response.ok()).toBeTruthy()
  const match = (await response.json() as DiagramList).items
    .find((diagram) => diagram.artifact_id === artifactId)
  expect(match, `expected diagram ${artifactId}`).toBeTruthy()
  return match as DiagramSummary
}

export async function captureStoredDiagram(
  page: Page,
  request: APIRequestContext,
  fileName: string,
  artifactId: string,
  provenance: CaptureProvenance,
): Promise<void> {
  const diagram = await diagramById(request, artifactId)
  const problems = watch(page)
  await page.goto(`/diagrams/${encodeURIComponent(diagram.artifact_id)}`, { waitUntil: 'load' })
  if (diagram.diagram_type !== 'matrix') await expect(page.locator('.svg-wrap svg')).toBeVisible({ timeout: 15_000 })
  await capture(page, fileName, provenance)
  expect(problems, `runtime problems while capturing ${fileName}`).toEqual([])
}

export async function captureRenderedDiagram(
  page: Page,
  request: APIRequestContext,
  fileName: string,
  artifactId: string,
  expectedLabel: string,
  provenance: CaptureProvenance,
): Promise<void> {
  await diagramById(request, artifactId)
  const svg = await request.get(`/api/diagrams/${encodeURIComponent(artifactId)}/svg`)
  expect(svg.ok()).toBeTruthy()
  expect(await svg.text(), `${fileName} should contain a stable label`).toContain(expectedLabel)
  const png = await request.get(
    `/api/diagrams/${encodeURIComponent(artifactId)}/download?format=png`,
  )
  expect(png.ok()).toBeTruthy()
  const dataUrl = `data:image/png;base64,${(await png.body()).toString('base64')}`
  await page.setContent(`<main id="render"><img alt="" src="${dataUrl}"></main><style>
    html,body,#render{width:100%;height:100%;margin:0}#render{display:flex;align-items:center;justify-content:center}
    img{display:block;max-width:100%;max-height:100%;object-fit:contain}
  </style>`)
  await page.screenshot({ path: mediaPath(fileName), animations: 'disabled' })
  record(fileName, provenance)
}

export async function addSyntheticBanner(page: Page): Promise<void> {
  await page.addInitScript(() => document.addEventListener('DOMContentLoaded', () => {
    const marker = document.createElement('div')
    marker.dataset.testid = 'synthetic-documentation-banner'
    marker.textContent = 'Synthetic documentation data'
    marker.style.cssText = 'background:#7c2d12;color:#fff;padding:8px 16px;font-weight:700;text-align:center;position:sticky;top:0;z-index:10000'
    document.body.prepend(marker)
  }))
}
