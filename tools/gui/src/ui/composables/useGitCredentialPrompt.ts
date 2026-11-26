import { inject, ref } from 'vue'
import type { Effect } from 'effect'
import { gitCredentialPromptKey, modelServiceKey } from '../keys'
import type { AskForGitCredential } from '../keys'
import type { RepoError } from '../../ports/repositoryErrors'
import {
  type GitCredentialAnswer,
  type GitCredentialRequest,
  withGitCredentials,
} from '../lib/gitCredentials'

/**
 * The app shell's one credential prompt: the request it is showing, and how it is answered.
 *
 * One dialog for the whole application, because a refused credential is a property of the backend
 * process, not of the view that happened to push, and two prompts open at once would ask for the
 * same secret twice. The answer is handed to whoever asked and then dropped; nothing here keeps it.
 */
export function useGitCredentialPrompt() {
  const pending = ref<GitCredentialRequest | null>(null)
  let settle: ((answer: GitCredentialAnswer | null) => void) | null = null

  const finish = (answer: GitCredentialAnswer | null): void => {
    const resolve = settle
    settle = null
    pending.value = null
    resolve?.(answer)
  }

  const ask: AskForGitCredential = (request) => {
    finish(null)
    pending.value = request
    return new Promise((resolve) => { settle = resolve })
  }

  return {
    pending,
    ask,
    submit: (answer: GitCredentialAnswer) => finish(answer),
    cancel: () => finish(null),
  }
}

/**
 * Wrap an operation that reaches the remote (save with push, submit, discard) so a refused git
 * credential is asked for and the operation repeated.
 *
 * Outside the app shell (a component test) nothing provides the prompt, and the operation runs as
 * it is.
 */
export function useGitCredentialRetry() {
  const svc = inject(modelServiceKey)!
  const ask = inject(gitCredentialPromptKey, null)
  return <A>(operation: () => Effect.Effect<A, RepoError>): Effect.Effect<A, RepoError> =>
    ask === null
      ? operation()
      : withGitCredentials(
          operation,
          (request, answer) => svc.supplyGitCredential({ protocol: request.protocol, ...answer }),
          ask,
        )
}
