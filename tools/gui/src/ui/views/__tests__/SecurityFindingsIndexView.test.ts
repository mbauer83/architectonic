import { describe, expect, it } from 'vitest'

import { indexState } from '../SecurityFindingsIndexView.helpers'
import type { SecuritySignalStats } from '../../../domain/schemas/assurance-security'

/**
 * The states of the page the nav's "Security findings" entry reaches.
 *
 * That entry used to mount `SecurityFindingsView`, which needs an entity id. With none it rendered
 * its header — *Active signal snapshot for* — followed by an empty link, and stopped: a sentence
 * fragment and no content, from a nav entry offering a working page. A finding belongs to an entity
 * and the read that returns one is a subresource of it, so there is no "every finding" answer; the
 * anchors are the answer.
 */

const stats = (over: Partial<SecuritySignalStats> = {}): SecuritySignalStats => ({
  total_snapshots: 0,
  assessed_entities: [],
  ...over,
})

const anchor = {
  entity_id: 'APP@1.aaaaaa.backend',
  snapshot_id: 'SNP@1',
  bom_component_count: 74,
  finding_count: 3,
}

describe('which state a security-signal read puts the index in', () => {
  it('lists the anchors when there are any', () => {
    expect(indexState(stats({ total_snapshots: 1, assessed_entities: [anchor] })))
      .toEqual({ kind: 'anchors' })
  })

  it('says nothing has been ingested when no snapshot exists', () => {
    expect(indexState(stats())).toEqual({ kind: 'no-snapshots' })
  })

  it('distinguishes snapshots that assess no entity from none at all', () => {
    expect(indexState(stats({ total_snapshots: 3 })))
      .toEqual({ kind: 'no-assessed-entities', snapshots: 3 })
  })

  it('carries a limited caller their reason instead of a claim about the store', () => {
    expect(indexState(stats({ reason: 'Above your classification ceiling.' })))
      .toEqual({ kind: 'limited', reason: 'Above your classification ceiling.' })
  })

  it('prefers the reason even where anchors came back', () => {
    expect(indexState(stats({ reason: 'Partial.', total_snapshots: 1, assessed_entities: [anchor] })))
      .toEqual({ kind: 'limited', reason: 'Partial.' })
  })

  it('treats absent fields as absent rather than as zero snapshots with anchors', () => {
    expect(indexState({})).toEqual({ kind: 'no-snapshots' })
  })
})
