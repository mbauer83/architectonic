import { Effect } from 'effect'
import type { RepoError } from '../../ports/repositoryErrors'
import { gitCredentialsRequiredDetails } from '../../domain/schemas/errors'
import { readApiErrorBody } from './errors'

/** What a refused git operation asks for: the protocol, the remote, and why it is asking. */
export interface GitCredentialRequest {
  readonly protocol: 'ssh' | 'https'
  readonly remote: string
  /** True when a credential was held and the remote refused it — the prompt says it was wrong. */
  readonly rejected: boolean
}

/** What the person entered. Lives only as long as the request that sends it. */
export interface GitCredentialAnswer {
  readonly secret: string
  readonly username?: string
}

/** The credential a failure asks for, or null when it failed for another reason. */
export const credentialRequestOf = (error: unknown): GitCredentialRequest | null => {
  const body = readApiErrorBody(error)
  const details = body === null ? null : gitCredentialsRequiredDetails(body)
  return details === null ? null : { protocol: details.protocol, remote: details.remote, rejected: details.rejected }
}

/** How many times one operation will ask before it reports the refusal as it stands. */
const MAX_PROMPTS = 3

/**
 * Run `operation`; when the remote refuses it for want of a git credential, ask for one, hand it to
 * the backend, and run the operation again.
 *
 * A credential the backend refuses while accepting it is asked for again, with the refusal's
 * reason, without repeating the operation in between. Cancelling the prompt fails with the original
 * refusal, so the caller shows what it would have shown without this.
 */
export const withGitCredentials = <A>(
  operation: () => Effect.Effect<A, RepoError>,
  supply: (request: GitCredentialRequest, answer: GitCredentialAnswer) => Effect.Effect<void, RepoError>,
  ask: (request: GitCredentialRequest) => Promise<GitCredentialAnswer | null>,
): Effect.Effect<A, RepoError> => {
  const askUntilAccepted = (request: GitCredentialRequest, prompts: number): Effect.Effect<boolean, RepoError> =>
    Effect.promise(() => ask(request)).pipe(
      Effect.flatMap((answer) =>
        answer === null
          ? Effect.succeed(false)
          : supply(request, answer).pipe(
              Effect.as(true),
              Effect.catchAll((refused) => {
                const again = credentialRequestOf(refused)
                return again === null || prompts + 1 >= MAX_PROMPTS
                  ? Effect.fail(refused)
                  : askUntilAccepted(again, prompts + 1)
              }),
            ),
      ),
    )

  const attempt = (prompts: number): Effect.Effect<A, RepoError> =>
    operation().pipe(
      Effect.catchAll((error) => {
        const request = credentialRequestOf(error)
        if (request === null || prompts >= MAX_PROMPTS) return Effect.fail(error)
        return askUntilAccepted(request, prompts).pipe(
          Effect.flatMap((supplied) => (supplied ? attempt(prompts + 1) : Effect.fail(error))),
        )
      }),
    )

  return attempt(0)
}
