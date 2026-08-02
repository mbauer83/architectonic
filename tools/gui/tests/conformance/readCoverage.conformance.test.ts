import { describe, expect, it } from 'vitest'
import { makeHttpModelRepository } from '../../src/adapters/http/HttpModelRepository'
import { READ_STEPS } from './readSteps'

/**
 * The harness's own completeness, held against the port rather than against a list of good
 * intentions.
 *
 * A conformance walk that quietly covers half the surface is the same class of artefact as the four
 * e2e tests in handoff 1 §1.1 that asserted a body the wire never carried: it reports success over
 * a question it never asked. So the port's methods are enumerated at run time, and every one is
 * either driven by a step or registered below with a reason. The register shrinks; it does not grow.
 */

/** Every method the port exposes, taken from a real adapter instance. */
const portMethods = (): readonly string[] =>
  Object.entries(makeHttpModelRepository())
    .filter(([, value]) => typeof value === 'function')
    .map(([name]) => name)

/**
 * Methods no step drives yet, each with why. Two kinds only:
 *
 * * **mutating** — creates, edits, deletes. They are the next slice (handoff §1.9 step 4) and need a
 *   fixture repository to write into; run against the dogfood repository they would author content.
 *   That every one of them is dark is not news: `NEVER_REQUESTED_OPERATIONS` says 73% of the write
 *   surface has never been requested at all.
 * * **needs a differently-started backend** — the admin tier answers 403 unless the server was
 *   started with `--admin-mode`, so a step here would assert the refusal, not the contract.
 */
const UNEXERCISED: Readonly<Record<string, string>> = {
  // Mutating — engagement tier.
  createEntity: 'mutating: authors an entity',
  editEntity: 'mutating: rewrites an entity',
  deleteEntity: 'mutating: removes an entity',
  addConnection: 'mutating: authors a connection',
  editConnection: 'mutating: rewrites a connection',
  removeConnection: 'mutating: removes a connection',
  manageConnectionAssociations: 'mutating: rewrites a set-valued relation',
  createDiagram: 'mutating: authors a diagram',
  editDiagram: 'mutating: replaces a diagram wholesale',
  deleteDiagram: 'mutating: removes a diagram',
  patchDiagramEntityMetadata: 'mutating: merges a metadata delta into a diagram',
  setEdgeLabel: 'mutating: writes an edge label into a diagram',
  syncDiagramToModel: 'mutating: promotes diagram content into the model',
  createDocument: 'mutating: authors a document',
  editDocument: 'mutating: rewrites a document',
  deleteDocument: 'mutating: removes a document',
  createMatrixDiagram: 'mutating: authors a matrix diagram',
  editMatrixDiagram: 'mutating: rewrites a matrix diagram',
  createGroup: 'mutating: authors a group',
  updateGroup: 'mutating: rewrites a group',
  renameGroup: 'mutating: renames a group, moving its members',
  archiveGroup: 'mutating: archives a group',
  unarchiveGroup: 'mutating: unarchives a group',
  deleteGroup: 'mutating: removes a group',
  createViewpointDefinition: 'mutating: authors a viewpoint definition',
  replaceViewpointDefinition: 'mutating: replaces a viewpoint definition',
  deleteViewpointDefinition: 'mutating: removes a viewpoint definition',
  setViewpointPins: 'mutating: rewrites the pin list',
  executePromotion: 'mutating: copies content into the enterprise repository',
  saveEngagementChanges: 'mutating: commits the engagement repository',
  saveEnterpriseChanges: 'mutating: commits the enterprise repository',
  submitEnterpriseChanges: 'mutating: opens an enterprise review',
  withdrawEnterpriseChanges: 'mutating: withdraws an enterprise review',

  // Admin tier — 403 unless the backend was started with --admin-mode.
  adminCreateEntity: 'admin-mode backend, and mutating',
  adminEditEntity: 'admin-mode backend, and mutating',
  adminDeleteEntity: 'admin-mode backend, and mutating',
  adminAddConnection: 'admin-mode backend, and mutating',
  adminRemoveConnection: 'admin-mode backend, and mutating',
  adminDeleteDiagram: 'admin-mode backend, and mutating',
  previewAdminDeleteEntity: 'admin-mode backend: without it the body is a refusal, not the contract',
  previewAdminRemoveConnection: 'admin-mode backend: the body would be a refusal',
  previewAdminDeleteDiagram: 'admin-mode backend: the body would be a refusal',

  // Not a request.
  diagramImageUrl: 'builds a URL for an <img> src; performs no request and decodes nothing',
}

describe('the conformance walk covers the port it claims to', () => {
  it('drives every repository method that is not registered as unexercised', () => {
    const driven = new Set(READ_STEPS.map((step) => step.method as string))
    const uncovered = portMethods()
      .filter((name) => !driven.has(name) && !(name in UNEXERCISED))
      .sort()
    expect(
      uncovered,
      'these repository methods are neither driven by a conformance step nor registered as '
        + 'unexercised. Add a step, or register one with a reason — the register only shrinks.',
    ).toEqual([])
  })

  it('registers nothing that a step now drives', () => {
    const driven = new Set(READ_STEPS.map((step) => step.method as string))
    const stale = Object.keys(UNEXERCISED).filter((name) => driven.has(name)).sort()
    expect(stale, 'a step drives these — remove them from UNEXERCISED').toEqual([])
  })

  it('registers nothing the port no longer has', () => {
    const present = new Set(portMethods())
    const stranded = Object.keys(UNEXERCISED).filter((name) => !present.has(name)).sort()
    expect(stranded, 'the port no longer has these — remove them from UNEXERCISED').toEqual([])
  })

  it('names every step after a method the port actually has', () => {
    const present = new Set(portMethods())
    const unknown = READ_STEPS.map((step) => step.method as string)
      .filter((name) => !present.has(name))
      .sort()
    expect(unknown, 'these steps name methods the port does not expose').toEqual([])
  })

  it('gives every registered exemption a reason', () => {
    const unreasoned = Object.entries(UNEXERCISED)
      .filter(([, reason]) => reason.trim().length < 15)
      .map(([name]) => name)
    expect(unreasoned).toEqual([])
  })
})
