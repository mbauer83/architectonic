import type { ModelRepository } from '../../ports/ModelRepository'
import {
  ScratchpadLiftSchema,
  ScratchpadListSchema,
  ScratchpadSchema,
} from '../../domain/schemas/scratchpads'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, deleteNoContent, fetchJson, postJson, putJson } from './httpTransport'

/**
 * The scratchpad half of the HTTP adapter.
 *
 * Six methods, matching the six routes and the six MCP tools. There is no `addNote` and no
 * `moveNote`: the resource is the aggregate, so the canvas mutates its own copy and saves the whole
 * thing. That is also what lets the canvas debounce — a per-note endpoint would put one request on
 * the wire per drag, which is the traffic shape the write path is least able to absorb.
 *
 * `replaceScratchpad` carries the version the client read. A mismatch is a 409 rather than an
 * overwrite: two people may have the same scratchpad open, and last-write-wins would discard an
 * afternoon of the other one's work without saying so.
 */

const scratchpadUrl = (id: string): string =>
  buildUrl(`/scratchpads/${encodeIdentitySegment(id)}`)

type ScratchpadMethods = Pick<
  ModelRepository,
  | 'listScratchpads'
  | 'getScratchpad'
  | 'createScratchpad'
  | 'replaceScratchpad'
  | 'deleteScratchpad'
  | 'liftScratchpad'
>

export const scratchpadMethods = (): ScratchpadMethods => ({
  listScratchpads: (params) =>
    fetchJson(buildUrl('/scratchpads', params), ScratchpadListSchema),
  getScratchpad: (id) => fetchJson(scratchpadUrl(id), ScratchpadSchema),
  createScratchpad: (body) => postJson(buildUrl('/scratchpads'), body, ScratchpadSchema),
  replaceScratchpad: (id, body) => putJson(scratchpadUrl(id), body, ScratchpadSchema),
  // `dry_run=false` because every write on this surface plans by default: a bare delete answers a
  // plan with 200, which reads as success and removes nothing.
  deleteScratchpad: (id) => deleteNoContent(`${scratchpadUrl(id)}?dry_run=false`),
  // The caller decides whether this is a rehearsal, so `dry-run` is passed through rather than
  // defaulted here: the dialog shows a plan first and executes the same call with it false.
  liftScratchpad: (id, body) =>
    postJson(`${scratchpadUrl(id)}/lift`, body, ScratchpadLiftSchema),
})
