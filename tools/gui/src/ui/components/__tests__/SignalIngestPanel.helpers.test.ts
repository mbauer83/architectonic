import { describe, expect, it } from 'vitest'

import {
  canAnchorSignals, changedTheStore, describeOutcome, parseSubmission, requestIdFor,
} from '../SignalIngestPanel.helpers'

const ADMISSIBLE = ['application-component', 'grouping', 'node']

describe('canAnchorSignals', () => {
  it('permits the types the backend declares', () => {
    expect(canAnchorSignals('application-component', ADMISSIBLE)).toBe(true)
    expect(canAnchorSignals('node', ADMISSIBLE)).toBe(true)
  })

  it('refuses anything else', () => {
    expect(canAnchorSignals('business-process', ADMISSIBLE)).toBe(false)
    expect(canAnchorSignals(undefined, ADMISSIBLE)).toBe(false)
  })

  it('offers nothing when the vocabulary could not be fetched', () => {
    /* An empty list means signals are unavailable, not that everything is
       permitted — failing open would show an ingest the API refuses. */
    expect(canAnchorSignals('application-component', [])).toBe(false)
  })
})

describe('parseSubmission', () => {
  const base = { bomText: '', vulnText: '' }

  it('accepts a BOM alone — an inventory-only snapshot is legitimate', () => {
    const parsed = parseSubmission({ ...base, bomText: '{"bomFormat":"CycloneDX"}' })

    expect(parsed.error).toBeUndefined()
    expect(parsed.bom).toEqual({ bomFormat: 'CycloneDX' })
    expect(parsed.vulnerabilities).toEqual([])
  })

  it('accepts a BOM with vulnerability records', () => {
    const parsed = parseSubmission({
      ...base, bomText: '{"bomFormat":"CycloneDX"}', vulnText: '[{"id":"CVE-1"}]',
    })

    expect(parsed.vulnerabilities).toEqual([{ id: 'CVE-1' }])
  })

  it('names which document failed, not just "invalid JSON"', () => {
    expect(parseSubmission({ ...base, bomText: '{' }).error).toMatch(/SBOM is not valid JSON/)
    expect(parseSubmission({
      ...base, bomText: '{"a":1}', vulnText: 'nope',
    }).error).toMatch(/vulnerability records are not valid JSON/)
  })

  it('rejects the wrong JSON shape in each field', () => {
    expect(parseSubmission({ ...base, bomText: '[1,2]' }).error).toMatch(/Expected a JSON object/)
    expect(parseSubmission({
      ...base, bomText: '{"a":1}', vulnText: '{"a":1}',
    }).error).toMatch(/Expected a JSON array/)
  })

  it('requires a BOM', () => {
    expect(parseSubmission(base).error).toMatch(/Paste a CycloneDX SBOM/)
  })
})

describe('describeOutcome', () => {
  it('reports PERSISTED counts and names the alias collapse', () => {
    /* The defect this wording exists to prevent: telling the user 41 findings
       when a read of the snapshot returns 24. */
    const message = describeOutcome(200, {
      status: 'activated', snapshot_id: 'SNAP@1',
      component_count: 107, finding_count: 24,
      submitted_finding_count: 41, collapsed_finding_count: 17,
    })

    expect(message).toContain('24 findings')
    expect(message).toContain('41 submitted')
    expect(message).toContain('17 collapsed')
  })

  it('omits the collapse clause when nothing collapsed', () => {
    const message = describeOutcome(200, {
      status: 'activated', snapshot_id: 'SNAP@1',
      component_count: 3, finding_count: 2,
      submitted_finding_count: 2, collapsed_finding_count: 0,
    })

    expect(message).not.toContain('collapsed')
    expect(message).toContain('2 findings')
  })

  it('says a replay wrote nothing', () => {
    const message = describeOutcome(200, { status: 'replayed', snapshot_id: 'SNAP@1' })

    expect(message).toContain('Nothing was written')
  })

  it('explains a conflict as a reused request id', () => {
    expect(describeOutcome(409, { status: 'conflict' })).toMatch(/new request id/)
  })

  it('surfaces each validation error', () => {
    const message = describeOutcome(422, {
      status: 'invalid',
      errors: [{ field: 'anchor_entity_id', message: 'anchor is required' }],
    })

    expect(message).toContain('anchor_entity_id: anchor is required')
  })

  it('reports a failed ingest as terminal, needing a new request id', () => {
    const message = describeOutcome(500, { status: 'failed', reason: 'OperationalError' })

    expect(message).toContain('OperationalError')
    expect(message).toMatch(/new request id/)
  })

  it('does not dress an unrecognised response as success', () => {
    expect(describeOutcome(404, { detail: 'Not Found' })).toMatch(/Unexpected response/)
  })
})

describe('changedTheStore', () => {
  it('is true only for an activation', () => {
    expect(changedTheStore({ status: 'activated' })).toBe(true)
    // A replay returns the stored outcome without writing, so nothing is stale.
    expect(changedTheStore({ status: 'replayed' })).toBe(false)
    expect(changedTheStore({ status: 'conflict' })).toBe(false)
  })
})

describe('requestIdFor', () => {
  /* request_id is an idempotency key — a machine concept a person pasting a BOM
     cannot meaningfully invent, so the form derives it instead of asking. */
  it('is stable for the same paste, so a retry replays instead of duplicating', () => {
    const submission = { bomText: '{"a":1}', vulnText: '[]' }

    expect(requestIdFor(submission)).toBe(requestIdFor({ ...submission }))
  })

  it('changes when the BOM changes, because that is a different request', () => {
    expect(requestIdFor({ bomText: '{"a":1}', vulnText: '' }))
      .not.toBe(requestIdFor({ bomText: '{"a":2}', vulnText: '' }))
  })

  it('changes when only the vulnerability records change', () => {
    expect(requestIdFor({ bomText: '{"a":1}', vulnText: '[]' }))
      .not.toBe(requestIdFor({ bomText: '{"a":1}', vulnText: '[{"id":"CVE-1"}]' }))
  })

  it('does not confuse a field boundary with content', () => {
    /* Concatenating the two fields without a separator would make ("ab","") and
       ("a","b") the same request. */
    expect(requestIdFor({ bomText: 'ab', vulnText: '' }))
      .not.toBe(requestIdFor({ bomText: 'a', vulnText: 'b' }))
  })
})
