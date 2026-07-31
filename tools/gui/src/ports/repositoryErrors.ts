import type { ParseResult } from 'effect'
import type { NetworkError } from '../domain'

/**
 * Errors that can come from any repository call.
 *
 * Declared beside the ports rather than inside one of them, so a port split by surface — the
 * engagement writes and the enterprise-admin writes now live in separate files — does not have to
 * import one interface's module just to name its error channel.
 */
export type RepoError = NetworkError | ParseResult.ParseError
