import { expect, test, type Page } from '@playwright/test'
import {
  addSyntheticBanner, capture, watch, type CaptureProvenance,
} from './mediaHelpers'

const BACKEND = 'APP@1777293133.OYEmP1.architecture-backend'

const syntheticProvenance = (testName: string): CaptureProvenance => ({
  test_name: testName,
  artifact_ids: [BACKEND],
  synthetic_augmentation: true,
})

const metrics = {
  availability: 'available', content_state: 'complete', basis_snapshot_id: 'SYNTHETIC-DOCS-001',
  basis_activated_at: '2026-07-22T00:00:00Z', computed_classification: 'TLP:WHITE', component_count: 1,
  finding_total: 1, open_component_findings: { direct: 1 }, distinct_open_vulnerabilities: 1,
  severity_band_counts: { high: 1 }, max_cvss_score: 8.1, max_severity_band: 'high',
  applicability_unknown_count: 0, unknown_severity_finding_count: 0, suppressed_finding_count: 0,
}

const findings = {
  count: 1, withheld: 0, findings: [{
    finding_id: 'SYNTHETIC-FINDING-001', canonical_vulnerability_id: 'CVE-2026-0001',
    severity_band: 'high', cvss_score: 8.1, applicability: 'applicable',
    provenance: '{"osv_id":"CVE-2026-0001"}', component_name: 'Architectonic Backend',
    component_purl: 'pkg:pypi/architectonic@0.0.0-docs', component_directness: 'direct',
  }],
}

const impact = {
  found: true, canonical_id: 'CVE-2026-0001', aliases: ['CVE-2026-0001'], affected_entity_count: 1,
  open_entity_count: 1, max_severity_band: 'high', max_cvss_score: 8.1, withheld_count: 0,
  affected: [{
    anchor_entity_id: BACKEND, snapshot_activated_at: '2026-07-22T00:00:00Z', open_component_count: 1,
    components: [{
      component_name: 'Architectonic Backend', component_purl: 'pkg:pypi/architectonic@0.0.0-docs',
      component_version: '0.0.0-docs', directness: 'direct', severity_band: 'high', cvss_score: 8.1,
      applicability: 'applicable', suppressed: false,
    }],
  }],
}

async function installSyntheticSecurity(page: Page): Promise<void> {
  await addSyntheticBanner(page)
  await page.route('**/api/assurance/security-metrics?*', (route) => route.fulfill({ json: metrics }))
  await page.route('**/api/assurance/security-findings?*', (route) => route.fulfill({ json: findings }))
  await page.route('**/api/assurance/vulnerability-impact?*', (route) => route.fulfill({ json: impact }))
}

async function focusSecurityPanel(page: Page): Promise<void> {
  await page.addStyleTag({ content: `
    .content-card,.document-reference-card,.connections-section,.lens-section,.signal-ingest{display:none!important}
  ` })
}

test('security entity metrics panel', async ({ page }) => {
  await installSyntheticSecurity(page)
  const problems = watch(page)
  await page.goto(`/entity?id=${encodeURIComponent(BACKEND)}`, { waitUntil: 'load' })
  await expect(page.locator('.derived-security')).toContainText('Derived security attributes')
  await expect(page.getByTestId('synthetic-documentation-banner')).toBeVisible()
  await focusSecurityPanel(page)
  await capture(page, 'security-entity-panel.png', syntheticProvenance('security entity metrics panel'))
  expect(problems).toEqual([])
})

test('locked security metrics state', async ({ page }) => {
  await page.route('**/api/assurance/status', (route) => route.fulfill({ json: { status: 'locked' } }))
  await page.route('**/api/assurance/security-metrics?*', (route) => route.fulfill({ status: 423, json: {
    error: 'store_locked', message: 'The assurance store is locked.',
  } }))
  const problems = watch(page)
  await page.goto(`/entity?id=${encodeURIComponent(BACKEND)}`, { waitUntil: 'load' })
  await expect(page.locator('.derived-security')).toHaveCount(0)
  const lockedIndicator = page.getByRole('link', { name: '🔒 Assurance' })
  await expect(lockedIndicator).toHaveAttribute('title', 'Assurance store locked')
  await capture(page, 'security-metrics-locked.png', {
    test_name: 'locked security metrics state', artifact_ids: [BACKEND], synthetic_augmentation: false,
  })
  expect(problems).toEqual([])
})

test('re-shoot security findings', async ({ page }) => {
  await installSyntheticSecurity(page)
  const problems = watch(page)
  await page.goto(`/assurance/security/findings?anchor=${encodeURIComponent(BACKEND)}`, { waitUntil: 'load' })
  await expect(page.getByTestId('component-group')).toContainText('Architectonic Backend')
  await capture(page, 'security-findings.png', syntheticProvenance('re-shoot security findings'))
  expect(problems).toEqual([])
})

test('re-shoot vulnerability impact', async ({ page }) => {
  await installSyntheticSecurity(page)
  const problems = watch(page)
  await page.goto('/assurance/security/vulnerability?id=CVE-2026-0001', { waitUntil: 'load' })
  await expect(page.getByTestId('impact-headline')).toContainText('1 entity affected')
  await capture(page, 'security-vulnerability-impact.png', syntheticProvenance('re-shoot vulnerability impact'))
  expect(problems).toEqual([])
})
