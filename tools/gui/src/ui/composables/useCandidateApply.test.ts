import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { CandidateApplication, OperationStanding } from '../../domain/schemas/candidates'
import { type CandidateApplyAccess, useCandidateApply } from './useCandidateApply'

const standing = (op: string, position: string): OperationStanding =>
  ({ operation: { op, artifact_id: 'APP@1.a' }, standing: position, reason: `${op} ${position}` })

/** A server that answers a dry run with *answer*, and an apply by integrating or refusing. */
const fakeAccess = (answer: Omit<CandidateApplication, 'dry_run' | 'integrated'>, refuseApply = false) => {
  const calls: string[] = []
  const access: CandidateApplyAccess = {
    applyCandidate: (id, dryRun) => {
      calls.push(`${dryRun ? 'preview' : 'apply'} ${id}`)
      if (!dryRun && refuseApply) {
        return Effect.fail(new NetworkError({ status: 409, message: `${id} cannot be applied: it drifted` }))
      }
      return Effect.succeed({ ...answer, dry_run: dryRun, integrated: !dryRun })
    },
  }
  return { access, calls }
}

describe('useCandidateApply', () => {
  it('previews with a dry run, and applies only once confirmed', async () => {
    const { access, calls } = fakeAccess({
      candidate: 'CAND-1', standing: [standing('edit_entity', 'applies'), standing('create_entity', 'already-there')],
    })
    const apply = useCandidateApply(access)

    await apply.open('CAND-1')
    expect(calls).toEqual(['preview CAND-1'])
    expect(apply.preview.value?.writes.map((one) => one.operation.op)).toEqual(['edit_entity'])
    expect(apply.preview.value?.skipped.map((one) => one.operation.op)).toEqual(['create_entity'])

    expect(await apply.confirm()).toBe(true)
    expect(calls).toEqual(['preview CAND-1', 'apply CAND-1'])
    expect(apply.preview.value).toBeNull()
  })

  it('carries the refusal a dry run answers', async () => {
    const { access } = fakeAccess({
      candidate: 'CAND-1', refusal: 'CAND-1 cannot be applied: it conflicts.', standing: [standing('x', 'conflicting')],
    })
    const apply = useCandidateApply(access)
    await apply.open('CAND-1')
    expect(apply.preview.value?.refusal).toBe('CAND-1 cannot be applied: it conflicts.')
  })

  it('keeps the preview open and says why when the apply itself is refused', async () => {
    const { access } = fakeAccess({ candidate: 'CAND-1', standing: [standing('edit_entity', 'applies')] }, true)
    const apply = useCandidateApply(access)
    await apply.open('CAND-1')

    expect(await apply.confirm()).toBe(false)
    expect(apply.error.value).toContain('it drifted')
    expect(apply.preview.value?.candidate).toBe('CAND-1')
    apply.close()
    expect(apply.preview.value).toBeNull()
    expect(apply.error.value).toBeNull()
  })

  it('does nothing on confirm when no preview is open', async () => {
    const { access, calls } = fakeAccess({ candidate: 'CAND-1', standing: [] })
    expect(await useCandidateApply(access).confirm()).toBe(false)
    expect(calls).toEqual([])
  })
})
