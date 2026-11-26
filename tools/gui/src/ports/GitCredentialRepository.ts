import type { Effect } from 'effect'
import type { RepoError } from './repositoryErrors'

/** A git credential for one protocol: the SSH key passphrase, or an HTTPS token and username. */
export interface GitCredentialSupply {
  readonly protocol: 'ssh' | 'https'
  readonly secret: string
  readonly username?: string
}

/**
 * Handing the backend a git credential a remote asked for.
 *
 * Its own port because it is about the backend process, not the model: the credential is kept in
 * the backend's memory until it stops, and nothing answers with it.
 */
export interface GitCredentialRepository {
  readonly supplyGitCredential: (body: GitCredentialSupply) => Effect.Effect<void, RepoError>
}
