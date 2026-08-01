import { type APIRequestContext, expect, test } from '@playwright/test'

/**
 * Runtime-wiring check for the STPA wizard's causal-chain step.
 *
 * The unit suite can only assert that the step declares a relation; it cannot show that
 * the declared relation is one the backend accepts. A wizard declaring a connection type
 * the ontology does not register fails silently — the POST is rejected and the link
 * simply never appears — so this drives the real UI against a live backend and reads the
 * edge back from the API.
 *
 * Fixture data lives in its own throwaway analysis and is removed again, so the test
 * neither depends on nor disturbs the analyses in the store.
 */

const ANALYSIS_NAME = 'Wizard causal-chain wiring check'

interface Fixture {
  analysisId: string
  ucaId: string
  hazardId: string
}

async function createNode(
  request: APIRequestContext,
  analysisId: string,
  nodeType: string,
  name: string,
  extra: Record<string, string> = {},
): Promise<string> {
  // Created inside its provenance analysis: the analysis is the address, and the body no longer
  // repeats it — a node cannot be created without recording which analysis produced it.
  const resp = await request.post(
    `/api/assurance/analyses/${encodeURIComponent(analysisId)}/nodes`, {
      data: { node_type: nodeType, name, ...extra },
    })
  expect(resp.status(), `creating a ${nodeType}`).toBe(200)
  const body = await resp.json() as { node_id: string }
  return body.node_id
}

async function stage(request: APIRequestContext): Promise<Fixture> {
  const created = await request.post('/api/assurance/analyses', {
    data: { name: ANALYSIS_NAME, method: 'STPA' },
  })
  expect(created.status(), 'the assurance store must be unlocked for this check').toBe(200)
  const { analysis_id: analysisId } = await created.json() as { analysis_id: string }

  const hazardId = await createNode(request, analysisId, 'hazard', 'Brakes are not applied in time')
  const controlActionId = await createNode(request, analysisId, 'control-action', 'Apply brakes')
  const ucaId = await createNode(
    request, analysisId, 'unsafe-control-action', 'Apply brakes — not-provided',
    { uca_type: 'not-provided' },
  )
  const concerns = await request.post('/api/assurance/edges', {
    data: { source_id: ucaId, target_id: controlActionId, conn_type: 'concerns' },
  })
  expect(concerns.status()).toBe(200)

  return { analysisId, ucaId, hazardId }
}

async function discard(request: APIRequestContext, analysisId: string): Promise<void> {
  const listed = await request.get(`/api/assurance/nodes?analysis_id=${encodeURIComponent(analysisId)}`)
  if (listed.ok()) {
    const { nodes } = await listed.json() as { nodes: { node_id: string }[] }
    for (const node of nodes) {
      await request.delete(`/api/assurance/nodes/${encodeURIComponent(node.node_id)}`)
    }
  }
  await request.delete(`/api/assurance/analyses/${encodeURIComponent(analysisId)}`)
}

test('the wizard links an unsafe control action to its hazard against a live backend', async ({ page, request }) => {
  const { analysisId, ucaId, hazardId } = await stage(request)

  try {
    await page.goto(`/assurance/analyses/${encodeURIComponent(analysisId)}/stpa`)
    await page.getByRole('button', { name: /UCAs/ }).click()

    const effects = page.locator('.effects')
    await expect(effects).toBeVisible()
    const linker = effects.locator('.node-row').filter({ hasText: 'not-provided' })
    await linker.getByLabel('Link leads-to hazard').selectOption({ label: 'Brakes are not applied in time' })

    // The wizard renders the confirmation only after the backend accepted the edge.
    await expect(linker.locator('.relation-set')).toHaveText('leads-to ✓')

    const edges = await request.get(`/api/assurance/edges?source_id=${encodeURIComponent(ucaId)}`)
    expect(edges.status()).toBe(200)
    const body = await edges.json() as { edges: { target_id: string; conn_type: string }[] }
    expect(body.edges).toContainEqual(
      expect.objectContaining({ target_id: hazardId, conn_type: 'leads-to' }),
    )
  } finally {
    await discard(request, analysisId)
  }
})
