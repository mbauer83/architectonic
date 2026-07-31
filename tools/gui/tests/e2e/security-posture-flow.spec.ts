import fs from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import {
  assertSecurityPostureFixture, BACKEND, installSecurityPostureFixture,
} from '../media/securityPostureFixture'

const METRICS = {
  availability: 'available', content_state: 'complete', basis_snapshot_id: 'SYNTHETIC-E2E-001',
  basis_activated_at: '2026-07-22T00:00:00Z', computed_classification: 'TLP:WHITE', component_count: 1,
  finding_total: 1, open_component_findings: { direct: 1 }, distinct_open_vulnerabilities: 1,
  severity_band_counts: { high: 1 }, max_cvss_score: 8.1, max_severity_band: 'high',
  applicability_unknown_count: 0, unknown_severity_finding_count: 0, suppressed_finding_count: 0,
}

async function selectBackendAnchor(page: Page): Promise<void> {
  const picker = page.getByPlaceholder('Search architecture elements for the SBOM scope…')
  await picker.fill('Architecture Backend')
  const result = page.locator('[data-result]').filter({ hasText: 'Architecture Backend' })
  await expect(result).toBeVisible({ timeout: 15_000 })
  await result.click()
  await expect(page.locator('.anchor-chip')).toContainText('Architecture Backend')
}

test('the colored security diagram exports a stamped classified SVG', async ({ page }) => {
  await installSecurityPostureFixture(page)
  await page.goto('/viewpoints/diagram?viewpoint=security-posture')
  await assertSecurityPostureFixture(page)

  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export stamped SVG' }).click()
  const download = await downloadEvent
  const path = await download.path()
  expect(path).not.toBeNull()
  const svg = fs.readFileSync(path as string, 'utf8')
  // What the export must prove is that the banner is burned in SERVER-side, from the store's
  // own view — not echoed back from whatever the client had on screen. The fixture stubs the
  // render endpoints with an available TLP:WHITE banner citing SYNTHETIC-DOCS-001; the export
  // goes through /api/viewpoints/export-render, which is not stubbed, so the stamped bytes
  // must disagree with the fixture and carry a freshly computed timestamp.
  //
  // Deliberately NOT asserted: a TLP band and a SNAP@ basis id. Both require an active signal
  // snapshot, which only exists after `arch-assurance seed --with-signals` reaches OSV over
  // the network. CI seeds from the committed bundle, and the export bundle cannot carry
  // snapshots at all, so asserting them made this test fail for a reason unrelated to the
  // behaviour under test. The unavailable-basis path is covered by the sibling test below.
  expect(svg).toContain('id="classification-banner"')
  expect(svg).toMatch(/generated \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/)
  expect(svg).not.toContain('SYNTHETIC-DOCS-001')
  expect(svg).not.toContain('2026-07-22T00:00:00Z')
})

test('an unavailable signal snapshot keeps the diagram usable and explains the fallback', async ({ page }) => {
  await page.route('**/api/viewpoints/execute-diagram', async (route) => {
    const response = await route.fetch()
    const body = await response.json() as Record<string, unknown>
    body.signal_banner = {
      classification: 'TLP:WHITE', available: false,
      note: 'signals unavailable: assurance store is locked', basis_snapshots: [],
      generated_at: '2026-07-22T00:00:00Z',
    }
    await route.fulfill({ response, json: body })
  })
  await page.goto('/viewpoints/diagram?viewpoint=security-posture')
  await expect(page.locator('.signal-banner')).toContainText('signals unavailable', { timeout: 30_000 })
  await expect(page.locator('.svg-wrap svg')).toBeVisible()
})

test('the supply-chain dashboard validates and records a contextual VEX assessment', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/assurance/arch-artifacts/*/security-metrics', (route) => route.fulfill({ json: METRICS }))
  await page.route('**/api/assurance/arch-artifacts/*/vex-assessments', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: { revision: 2 } })
  })

  await page.goto('/assurance/supply-chain')
  await selectBackendAnchor(page)
  await page.getByRole('button', { name: /Posture & VEX/ }).click()
  await expect(page.locator('.metric-grid')).toContainText('8.1 (high)')

  const form = page.locator('.vex-form')
  await form.getByPlaceholder(/component \(purl/).fill('pkg:pypi/architectonic@1.0.0')
  await form.getByPlaceholder('canonical vulnerability id (VID@…)').fill('VID@synthetic-001')
  await form.locator('select').selectOption('not_affected')
  await form.getByPlaceholder('author').fill('documentation acceptance')
  await form.getByRole('button', { name: 'Record assessment' }).click()
  await expect(form).toContainText('requires a justification')

  await form.getByPlaceholder(/justification/).fill('The vulnerable code path is not included.')
  await form.getByRole('button', { name: 'Record assessment' }).click()
  await expect(form).toContainText('recorded revision 2')
  // No `anchor_entity_id`: the anchor is the address the assessment is posted to, so a body that
  // named one would give the caller two places to say which artifact it assessed.
  expect(submitted).not.toHaveProperty('anchor_entity_id')
  expect(submitted).toMatchObject({
    canonical_component_id: 'pkg:pypi/architectonic@1.0.0',
    canonical_vulnerability_id: 'VID@synthetic-001',
    vex_status: 'not_affected', author: 'documentation acceptance',
  })
})

test('derived security attributes stay read-only and disappear when locked', async ({ page }) => {
  await page.route('**/api/assurance/arch-artifacts/*/security-metrics', (route) => route.fulfill({ json: METRICS }))
  await page.goto(`/entity?id=${encodeURIComponent(BACKEND)}`)
  const panel = page.locator('.derived-security')
  await expect(panel).toContainText('Derived security attributes')
  await expect(panel).toContainText('8.1')
  await expect(panel.locator('input, select, textarea, button')).toHaveCount(0)

  await page.unroute('**/api/assurance/arch-artifacts/*/security-metrics')
  await page.route('**/api/assurance/arch-artifacts/*/security-metrics', (route) => route.fulfill({
    status: 423, json: { error: 'store_locked', message: 'The assurance store is locked.' },
  }))
  await page.reload()
  await expect(page.locator('.derived-security')).toHaveCount(0)
})
