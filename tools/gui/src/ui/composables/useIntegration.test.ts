/**
 * Integrating candidates from the Integration tab: every resolution is asked of the server over all made so
 * far, a refused one is not kept, taking one back takes back those made after it, and Integrate writes only
 * once no conflict stands.
 */
import { Effect } from 'effect'
import { describe, expect, it, vi } from 'vitest'
import type { CandidateIntegration, Resolution } from '../../domain/schemas/candidates'
import { type IntegrationAccess, useIntegration } from './useIntegration'

const conflict = {
  kind: 'same-key', subject: 'name of SRV@1.svc', actions: ['take', 'drop', 'merge'],
  parties: [{ set_id: 'A', operation: {} }, { set_id: 'B', operation: {} }],
}
const answer = (conflicts: number, integration?: string): CandidateIntegration => ({
  candidates: ['A', 'B'], dry_run: integration === undefined, operations: 2,
  conflicts: Array.from({ length: conflicts }, () => conflict),
  ...(integration ? { integration: { record: { id: integration }, version: 'v1' } } : {}),
})
const take = (party: string): Resolution => ({ kind: 'same-key', subject: 'name of SRV@1.svc', action: 'take', party })

const access = (reply: (resolutions: readonly Resolution[], dryRun: boolean) => CandidateIntegration | null) => {
  const integrateCandidates = vi.fn((body: { resolutions: readonly Resolution[]; dry_run: boolean }) => {
    const read = reply(body.resolutions, body.dry_run)
    return read ? Effect.succeed(read) : Effect.fail({ _tag: 'HttpError', status: 422, message: 'No conflict' })
  })
  return { integrateCandidates, createDocument: vi.fn() } as unknown as IntegrationAccess & {
    integrateCandidates: typeof integrateCandidates
  }
}

describe('integrating candidates', () => {
  it('asks again with each resolution, and integrates once none stands', async () => {
    const svc = access((resolutions, dryRun) => (dryRun ? answer(resolutions.length ? 0 : 1) : answer(0, 'CAND@9.int')))
    const integrated = vi.fn()
    const integration = useIntegration(svc, integrated)

    await integration.choose(['A', 'B'])
    expect(integration.answer.value?.conflicts).toHaveLength(1)
    expect(integration.ready.value).toBe(false)

    await integration.resolve(take('B'))
    expect(svc.integrateCandidates).toHaveBeenLastCalledWith(expect.objectContaining({ resolutions: [take('B')] }))
    expect(integration.ready.value).toBe(true)

    await integration.integrate()
    expect(svc.integrateCandidates).toHaveBeenLastCalledWith(expect.objectContaining({ dry_run: false }))
    expect(integrated).toHaveBeenCalledWith('CAND@9.int')
  })

  it('does not keep a resolution the server refuses, and says why', async () => {
    const svc = access((resolutions) => (resolutions.length ? null : answer(1)))
    const integration = useIntegration(svc, () => {})
    await integration.choose(['A', 'B'])

    await integration.resolve(take('Z'))

    expect(integration.resolutions.value).toEqual([])
    expect(integration.error.value).toBeTruthy()
    expect(integration.answer.value?.conflicts).toHaveLength(1)
  })

  it('takes back a resolution with every one made after it', async () => {
    const svc = access((resolutions) => answer(Math.max(0, 2 - resolutions.length)))
    const integration = useIntegration(svc, () => {})
    await integration.choose(['A', 'B'])
    await integration.resolve(take('A'))
    await integration.resolve(take('B'))

    await integration.takeBack(0)

    expect(integration.resolutions.value).toEqual([])
    expect(integration.answer.value?.conflicts).toHaveLength(2)
  })
})
