import { describe, expect, it, vi } from 'vitest'
import { Effect, Either } from 'effect'
import { NetworkError } from '../../domain'
import type { RepoError } from '../../ports/repositoryErrors'
import {
  credentialRequestOf,
  type GitCredentialAnswer,
  type GitCredentialRequest,
  withGitCredentials,
} from './gitCredentials'

const REMOTE = 'git@git.example.invalid:acme/enterprise.git'

const refusal = (rejected: boolean): NetworkError =>
  new NetworkError({
    status: 409,
    message: JSON.stringify({
      detail: {
        code: 'git_credentials_required',
        message: 'The SSH key passphrase for origin is needed.',
        details: { protocol: 'ssh', remote: REMOTE, rejected },
        request_id: 'r-1',
      },
    }),
  })

const other = new NetworkError({ status: 500, message: 'Failed to push: remote hung up' })

/** An operation that fails with each of `failures` in turn, then succeeds. */
const failingThen = (failures: NetworkError[]) => {
  const calls = { count: 0 }
  const operation = () => {
    const failure = failures[calls.count]
    calls.count += 1
    return failure === undefined ? Effect.succeed('pushed') : Effect.fail(failure)
  }
  return { operation, calls }
}

const run = <A>(effect: Effect.Effect<A, RepoError>) => Effect.runPromise(Effect.either(effect))

describe('credentialRequestOf', () => {
  it('reads the protocol, remote and reason from the refusal', () => {
    expect(credentialRequestOf(refusal(true))).toEqual({ protocol: 'ssh', remote: REMOTE, rejected: true })
  })

  it('is null for any other failure', () => {
    expect(credentialRequestOf(other)).toBeNull()
  })
})

describe('withGitCredentials', () => {
  it('asks once, supplies the answer and repeats the operation', async () => {
    const { operation, calls } = failingThen([refusal(false)])
    const supplied: GitCredentialAnswer[] = []
    const ask = vi.fn(() => Promise.resolve({ secret: 'open sesame' }))

    const result = await run(withGitCredentials(
      operation, (_request, answer) => { supplied.push(answer); return Effect.void }, ask,
    ))

    expect(result).toEqual(Either.right('pushed'))
    expect(calls.count).toBe(2)
    expect(ask).toHaveBeenCalledWith({ protocol: 'ssh', remote: REMOTE, rejected: false })
    expect(supplied).toEqual([{ secret: 'open sesame' }])
  })

  it('asks again with the reason when the backend refuses the credential, without repeating the operation', async () => {
    const { operation, calls } = failingThen([refusal(false)])
    const asked: GitCredentialRequest[] = []
    const answers = ['wrong', 'right']
    const ask = (request: GitCredentialRequest) => { asked.push(request); return Promise.resolve({ secret: answers.shift()! }) }
    const supply = (_request: GitCredentialRequest, answer: GitCredentialAnswer) =>
      answer.secret === 'right' ? Effect.void : Effect.fail(refusal(true))

    const result = await run(withGitCredentials(operation, supply, ask))

    expect(result).toEqual(Either.right('pushed'))
    expect(asked.map((request) => request.rejected)).toEqual([false, true])
    expect(calls.count).toBe(2)
  })

  it('fails with the original refusal when the person cancels', async () => {
    const original = refusal(false)
    const { operation, calls } = failingThen([original])
    const supply = vi.fn(() => Effect.void)

    const result = await run(withGitCredentials(operation, supply, () => Promise.resolve(null)))

    expect(result).toEqual(Either.left(original))
    expect(supply).not.toHaveBeenCalled()
    expect(calls.count).toBe(1)
  })

  it('passes any other failure through without asking', async () => {
    const { operation } = failingThen([other])
    const ask = vi.fn(() => Promise.resolve({ secret: 'x' }))

    const result = await run(withGitCredentials(operation, () => Effect.void, ask))

    expect(result).toEqual(Either.left(other))
    expect(ask).not.toHaveBeenCalled()
  })

  it('stops asking after three prompts', async () => {
    const { operation } = failingThen([refusal(false), refusal(true), refusal(true), refusal(true)])
    const ask = vi.fn(() => Promise.resolve({ secret: 'accepted but still refused on push' }))

    const result = await run(withGitCredentials(operation, () => Effect.void, ask))

    expect(Either.isLeft(result)).toBe(true)
    expect(ask).toHaveBeenCalledTimes(3)
  })
})
