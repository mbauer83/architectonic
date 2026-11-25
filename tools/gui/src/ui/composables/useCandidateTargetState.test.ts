import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { TargetStateIds } from '../../domain/schemas/candidates'
import { type CandidateTargetStateAccess, type TargetWrite, useCandidateTargetState } from './useCandidateTargetState'

const IDS: TargetStateIds = {
  baseline: 'PLT@1.a', target: 'PLT@1.b', gap: 'ASS@1.c', copies: { 'APP@1.d': 'APP@1.e' }, added: {},
}
const CREATE = { op: 'create_entity', fields: { name: 'Ledger (target)' } }

/** A server holding one candidate, applied as a target state once the apply is confirmed. */
const fakeAccess = (refuseMove = false, held: string | null = null) => {
  const calls: string[] = []
  let recorded: TargetStateIds | null = null
  const access: CandidateTargetStateAccess = {
    readCandidate: (id) => Effect.succeed({ record: { id, ...(recorded ? { 'target-state': recorded } : {}) }, version: 'v' }),
    applyCandidateAsTargetState: (id, dryRun) => {
      calls.push(`${dryRun ? 'preview' : 'write'} apply ${id}`)
      if (!dryRun) recorded = IDS
      return Effect.succeed({
        candidate: id, dry_run: dryRun, applied: !dryRun, standing: [], target_state: IDS, operations: [CREATE],
      })
    },
    moveCandidateIntoBaseline: (id, dryRun) => {
      calls.push(`${dryRun ? 'preview' : 'write'} move ${id}`)
      if (!dryRun && refuseMove) return Effect.fail(new NetworkError({ status: 409, message: 'it drifted' }))
      if (!dryRun) recorded = null
      return Effect.succeed({ candidate: id, dry_run: dryRun, integrated: !dryRun, standing: [], operations: [] })
    },
    withdrawCandidateTargetState: (id, dryRun) => {
      calls.push(`${dryRun ? 'preview' : 'write'} withdraw ${id}`)
      if (held) return Effect.succeed({ candidate: id, dry_run: dryRun, released: false, refusal: held, operations: [] })
      if (!dryRun) recorded = null
      return Effect.succeed({ candidate: id, dry_run: dryRun, released: !dryRun, operations: [CREATE] })
    },
  }
  return { access, calls }
}

describe('useCandidateTargetState', () => {
  it('previews an apply, writes it only once confirmed, and then reads where it stands', async () => {
    const { access, calls } = fakeAccess()
    const told: TargetWrite[] = []
    const target = useCandidateTargetState(access, (write) => told.push(write))
    await target.load('CAND-1')
    expect(target.standing.value).toBeNull()

    await target.open('apply', 'CAND-1')
    expect(target.preview.value?.ids).toEqual(IDS)
    expect(target.preview.value?.operations).toEqual([CREATE])
    expect(calls).toEqual(['preview apply CAND-1'])

    expect(await target.confirm()).toBe(true)
    expect(told).toEqual(['apply'])
    expect(target.standing.value).toEqual(IDS)
    expect(target.preview.value).toBeNull()
  })

  it('moves into the baseline, after which nothing stands', async () => {
    const { access, calls } = fakeAccess()
    const target = useCandidateTargetState(access)
    await target.open('apply', 'CAND-1')
    await target.confirm()
    await target.open('move', 'CAND-1')
    expect(await target.confirm()).toBe(true)
    expect(calls.slice(-2)).toEqual(['preview move CAND-1', 'write move CAND-1'])
    expect(target.standing.value).toBeNull()
  })

  it('keeps a refused move open and says why', async () => {
    const { access } = fakeAccess(true)
    const target = useCandidateTargetState(access)
    await target.open('move', 'CAND-1')
    expect(await target.confirm()).toBe(false)
    expect(target.preview.value?.write).toBe('move')
    expect(target.error.value).toContain('it drifted')
  })

  it('withdraws a target state after its dry run, after which nothing stands', async () => {
    const { access, calls } = fakeAccess()
    const told: TargetWrite[] = []
    const target = useCandidateTargetState(access, (write) => told.push(write))
    await target.open('apply', 'CAND-1')
    await target.confirm()
    await target.open('withdraw', 'CAND-1')
    expect(target.preview.value?.write).toBe('withdraw')
    expect(await target.confirm()).toBe(true)
    expect(calls.slice(-2)).toEqual(['preview withdraw CAND-1', 'write withdraw CAND-1'])
    expect(told).toEqual(['apply', 'withdraw'])
    expect(target.standing.value).toBeNull()
  })

  it('shows what holds on to a target state and writes nothing', async () => {
    const { access, calls } = fakeAccess(false, 'the diagram DIA@1.x draws it')
    const target = useCandidateTargetState(access)
    await target.open('withdraw', 'CAND-1')
    expect(target.preview.value?.refusal).toContain('DIA@1.x')
    expect(calls).toEqual(['preview withdraw CAND-1'])
  })
})
