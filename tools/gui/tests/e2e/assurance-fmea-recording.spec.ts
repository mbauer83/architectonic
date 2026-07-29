import { type APIRequestContext, expect, test } from '@playwright/test'

/**
 * Answering a cell from the matrix, against a live backend.
 *
 * The unit suite can show that the form builds the right request; it cannot show that the request is
 * one the backend accepts, or that the answer comes back changed. That gap is not hypothetical here:
 * the factor endpoint was served for a long time while no GUI path called it at all, so the cells
 * could be read and never answered, and every unit test around them still passed.
 *
 * Fixture data lives in its own throwaway analysis and is removed again, so this neither depends on
 * nor disturbs the analyses in the store.
 */

const ANALYSIS_NAME = 'Occurrence recording wiring check'
const GUIDEWORD = 'no-function'

interface Fixture {
  analysisId: string
  failureModeId: string
  elementId: string
}

async function createNode(
  request: APIRequestContext,
  analysisId: string,
  nodeType: string,
  name: string,
  extra: Record<string, string> = {},
): Promise<string> {
  const resp = await request.post('/api/assurance/nodes', {
    data: { node_type: nodeType, name, analysis_id: analysisId, ...extra },
  })
  expect(resp.status(), `creating a ${nodeType}`).toBe(200)
  return ((await resp.json()) as { node_id: string }).node_id
}

/**
 * A failure mode that reaches a severe loss and has nothing detecting it.
 *
 * Both halves matter: severity and detectability are derived, and occurrence is asked for only where
 * it could still change the band. A staged row with a mild loss would render no field to fill in,
 * and the test would be asserting the absence of the thing it means to exercise.
 */
async function stage(request: APIRequestContext): Promise<Fixture> {
  const created = await request.post('/api/assurance/analyses', {
    data: { name: ANALYSIS_NAME, method: 'FMEA' },
  })
  expect(created.status(), 'the assurance store must be unlocked for this check').toBe(200)
  const { analysis_id: analysisId } = await created.json() as { analysis_id: string }

  const elementId = 'APP@1777293133.OYEmP1.architecture-backend'
  const controller = await createNode(request, analysisId, 'control-structure-node', 'Recorded element')
  await request.post('/api/assurance/arch-refs', {
    data: { assurance_node_id: controller, arch_artifact_id: elementId, ref_type: 'binds-to' },
  })

  const lossId = await createNode(request, analysisId, 'loss', 'Analysis records are lost')
  const hazardId = await createNode(request, analysisId, 'hazard', 'Records are written unverified')
  await request.post('/api/assurance/edges', {
    data: { source_id: hazardId, target_id: lossId, conn_type: 'leads-to' },
  })

  const failureModeId = await createNode(
    request, analysisId, 'failure-mode', 'The element stops writing records',
    { failure_type: GUIDEWORD, concern_class: 'safety' },
  )
  await request.post('/api/assurance/arch-refs', {
    data: { assurance_node_id: failureModeId, arch_artifact_id: elementId, ref_type: 'binds-to' },
  })
  await request.post('/api/assurance/edges', {
    data: { source_id: failureModeId, target_id: hazardId, conn_type: 'leads-to' },
  })

  return { analysisId, failureModeId, elementId }
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

test('an occurrence recorded from the matrix reaches the store and comes back', async ({ page, request }) => {
  const { analysisId, failureModeId } = await stage(request)

  try {
    await page.goto('/assurance/fmea')
    await expect(page.getByRole('heading', { name: 'FMEA Matrix' })).toBeVisible()

    const opener = page.getByRole('button', { name: 'Record occurrence' }).first()
    await expect(opener, 'a row awaiting an occurrence must offer somewhere to record it')
      .toBeVisible({ timeout: 15_000 })
    await opener.click()

    const form = page.locator('form.occ')
    await expect(form).toBeVisible()

    // The value is never pre-filled: a selected member would read as the tool's opinion, and the
    // rationale beneath it as agreement with the tool rather than a judgement of someone's own.
    await expect(form.locator('select')).toHaveValue('')
    // The rationale is pre-filled, because the facts are what the model already knows.
    await expect(form.locator('textarea')).not.toHaveValue('')

    await form.locator('select').selectOption({ index: 1 })
    await form.getByRole('textbox').first().fill('End-to-end wiring check')
    await form.locator('textarea').fill('Judged against the facts shown above.')
    await form.getByRole('button', { name: 'Record occurrence' }).click()

    // Read back from the API, not from the page: the point is that the judgement was stored, and a
    // form that cleared itself optimistically would look identical here.
    await expect.poll(async () => {
      const resp = await request.get('/api/assurance/fmea')
      const body = await resp.json() as {
        rows: { cells: { node_id: string | null; factors: Record<string, { value: string | null }> }[] }[]
      }
      const cell = body.rows
        .flatMap((row) => row.cells)
        .find((candidate) => candidate.node_id === failureModeId)
      return cell?.factors.occurrence?.value ?? null
    }, {
      message: 'the recorded occurrence never appeared on the cell',
      timeout: 15_000,
    }).not.toBeNull()
  } finally {
    await discard(request, analysisId)
  }
})
