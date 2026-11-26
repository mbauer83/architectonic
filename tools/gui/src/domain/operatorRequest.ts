import type { operations } from './schemas/openapi.generated'

/**
 * The header that makes a request from this GUI a local operator request.
 *
 * The backend accepts a few process-level operations — supplying a git credential is one — only from
 * the loopback carrying this header. A page from another origin cannot attach it without a CORS
 * preflight the backend does not grant, so sending it is what distinguishes this GUI, served by the
 * backend itself, from anything else in the same browser.
 *
 * Its name is typed against the published document: the credentials operation declares the header,
 * so a rename on the server is a type error here rather than a refusal at run time.
 */
type CredentialRequestHeaders = NonNullable<operations['sync_supply_credentials']['parameters']['header']>

export const OPERATOR_REQUEST_HEADER: keyof CredentialRequestHeaders & string = 'X-Arch-Operator-Request'

export const operatorRequestHeaders = (): Readonly<Record<string, string>> => ({ [OPERATOR_REQUEST_HEADER]: '1' })
