import { describe, expect, it } from 'vitest'
import { makeHttpModelRepository } from '../../src/adapters/http/HttpModelRepository'
import { READ_STEPS } from './readSteps'
import { ADMIN_WRITE_STEPS, WRITE_STEPS } from './writeSteps'

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
 * Methods no step drives, each with why. **One entry, as of 2026-08-02.**
 *
 * It held 42: every mutating method, plus the whole admin tier. Both kinds had the same precondition —
 * a repository they could write into, and for the admin tier a backend started with `--admin-mode` —
 * and both are met now by `tools/quality/gui_write_walk.py`, which builds a disposable workspace, serves
 * it on its own port, and runs the write harness against it twice: once per tier, sequentially, because
 * admin mode is process-wide.
 *
 * Two defects came out of the first run, both invisible for exactly as long as these methods were dark:
 * `patchDiagramEntityMetadata` sent `attribute_id` in the body, which the server had moved into the path
 * and now forbids outright — so every attribute-metadata edit in the shipped UI answered 422 — and the
 * port declared `adminDeleteDiagram` with no way to create the diagram it deletes.
 *
 * What is left is not a request at all.
 *
 * **What this register does not cover, and cannot: the assurance surface.** `portMethods()` reads a
 * `ModelRepository` instance, and the GUI's `/api/assurance/*` calls go through no port — they are
 * `fetch` calls written directly in about thirty components and helpers, from `AssuranceStpaWizardView`
 * and `FmeaMatrixPanel` to `SignalIngestPanel` and `VulnerabilityImpactView`. There is no
 * `HttpAssuranceRepository` beside `HttpModelRepository`.
 *
 * So an empty register here means *every port method is driven*, and says nothing whatever about the
 * assurance client. Worth stating plainly, because "UNEXERCISED: 0" reads as though the GUI were fully
 * covered, and a handoff written against that reading planned a slice of work on a premise that was
 * false. The 38 dark `/api/assurance/*` operations retired on 2026-08-03 were retired by
 * `tools/quality/rest_write_walk.py` and `rest_read_walk.py` — at the *route* level. Five Playwright
 * specs (`assurance-stpa-wizard`, `assurance-fmea-recording`, `assurance-browse-parity`,
 * `assurance-graph-explore`, `security-posture-flow`) cover part of the client level. The rest of the
 * assurance client is exercised by nothing, and no register can currently say so.
 *
 * Closing that means an assurance port and adapter with its schemas held against
 * `openapi.generated.ts` — the same arrangement the model surface has, and by CLAUDE.md's
 * architectural-discipline rule the principled fix rather than more specs bolted onto the outside. It
 * is a ~30-file refactor of a different concern and is deliberately not bundled with the fixture store;
 * this comment is the record that it is known rather than overlooked.
 */
const UNEXERCISED: Readonly<Record<string, string>> = {
  // Not a request.
  diagramImageUrl: 'builds a URL for an <img> src; performs no request and decodes nothing',
}

/** Every method any walk drives — reads, engagement writes, admin writes. */
const drivenMethods = (): Set<string> =>
  new Set(
    [...READ_STEPS, ...WRITE_STEPS, ...ADMIN_WRITE_STEPS].map((step) => step.method as string),
  )

describe('the conformance walk covers the port it claims to', () => {
  it('drives every repository method that is not registered as unexercised', () => {
    const driven = drivenMethods()
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
    const driven = drivenMethods()
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
    const unknown = [...drivenMethods()].filter((name) => !present.has(name)).sort()
    expect(unknown, 'these steps name methods the port does not expose').toEqual([])
  })

  it('gives every registered exemption a reason', () => {
    const unreasoned = Object.entries(UNEXERCISED)
      .filter(([, reason]) => reason.trim().length < 15)
      .map(([name]) => name)
    expect(unreasoned).toEqual([])
  })
})
