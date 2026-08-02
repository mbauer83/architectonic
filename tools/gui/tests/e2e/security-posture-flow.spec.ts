import fs from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import {
  assertSecurityPostureFixture, BACKEND, installSecurityPostureFixture,
} from '../media/securityPostureFixture'

/**
 * The *scenario* these two tests need, laid over the real metrics body.
 *
 * It used to be a hand-built seventeen-field object, and it had already drifted: the server sends
 * `visibility_limited`, which the literal did not have. A body a test invents is a body no contract
 * check can reach — it passes for exactly as long as nobody looks, which is how four e2e tests came
 * to assert an error shape the wire never carried. Fetching the real response and overriding only
 * what the scenario states is the pattern the sibling test below already used for
 * `execute-diagram`; this spreads it.
 *
 * Ten fields, because the premise is "an active snapshot anchors this entity and carries one high
 * finding" — `panelVisible` gates on the basis id, and a local store with no active snapshot has
 * neither. That premise is the test's own; it is not the contract. The other seven,
 * `visibility_limited` and `availability` among them, still come from the server, and a change to
 * any of them fails here.
 */
const withFindings = {
  content_state: 'complete',
  basis_snapshot_id: 'SNAP@e2e-simulated',
  basis_activated_at: '2026-07-22T00:00:00Z',
  component_count: 1,
  finding_total: 1,
  open_component_findings: { direct: 1 },
  distinct_open_vulnerabilities: 1,
  severity_band_counts: { high: 1 },
  max_cvss_score: 8.1,
  max_severity_band: 'high',
}

const routeMetricsOverriding = async (page: Page, patch: Record<string, unknown>): Promise<void> => {
  await page.route('**/api/assurance/arch-artifacts/*/security-metrics', async (route) => {
    const response = await route.fetch()
    const body = { ...(await response.json() as Record<string, unknown>), ...patch }
    await route.fulfill({ response, json: body })
  })
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
  await page.goto('/viewpoints/security-posture/diagram')
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
  await page.goto('/viewpoints/security-posture/diagram')
  await expect(page.locator('.signal-banner')).toContainText('signals unavailable', { timeout: 30_000 })
  await expect(page.locator('.svg-wrap svg')).toBeVisible()
})

test('the supply-chain dashboard validates and records a contextual VEX assessment', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await routeMetricsOverriding(page, withFindings)
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
  await routeMetricsOverriding(page, withFindings)
  await page.goto(`/entities/${encodeURIComponent(BACKEND)}`)
  const panel = page.locator('.derived-security')
  await expect(panel).toContainText('Derived security attributes')
  await expect(panel).toContainText('8.1')
  await expect(panel.locator('input, select, textarea, button')).toHaveCount(0)

  await page.unroute('**/api/assurance/arch-artifacts/*/security-metrics')
  // A *simulated state*, so this one stays a fulfil — there is no real locked response to fetch
  // while the store is open. The body is the typed envelope the surface actually serves, though:
  // it read `{error, message}`, which is the pre-0.2.0 shape and would have kept passing while the
  // client's branch on `detail.code` fell through.
  await page.route('**/api/assurance/arch-artifacts/*/security-metrics', (route) => route.fulfill({
    status: 423,
    json: {
      detail: {
        code: 'assurance_store_locked',
        message: 'The confidential assurance store is not unlocked.',
        details: null,
        request_id: 'e2e-simulated-lock',
      },
    },
  }))
  await page.reload()
  await expect(page.locator('.derived-security')).toHaveCount(0)
})
