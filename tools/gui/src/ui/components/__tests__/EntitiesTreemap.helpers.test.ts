/**
 * The entity treemap's two grouping axes and its one sizing rule.
 *
 * @verifies REQ@1777372175.eFz3z9
 *
 * The requirement asks for a treemap "grouped by ArchiMate domain and entity-type, size by total number
 * of connections". Both axes are asserted here, and the sizing with them, because the register recorded
 * this as a partial implementation on the strength of a name: the second axis is spelled `subdomain` on
 * an `EntitySummary`, and `subdomain` *is* the entity type — an entity is filed at
 * `model/<domain>/<artifact-type>/` and the backend reads the subdomain out of that segment.
 * `tests/application/test_treemap_second_axis_is_entity_type.py` holds that half; this holds the half
 * about what the treemap does with it.
 *
 * The fixtures below are this file's own, so the counts are exact — which they could not be against the
 * live model, where authoring an entity would change them.
 */
import { describe, expect, it } from 'vitest'

import type { EntitySummary } from '../../../domain'
import {
  entityTreemapGroups,
  groupModeFor,
  groupNameOf,
  treemapNote,
} from '../EntitiesTreemap.helpers'

const entity = (over: Partial<EntitySummary>): EntitySummary => ({
  artifact_id: 'APP@1700000000.aaaaaa.thing',
  artifact_type: 'application-component',
  name: 'Thing',
  version: '0.1.0',
  status: 'active',
  domain: 'application',
  subdomain: 'application-component',
  path: '/model/application/application-component/APP@1700000000.aaaaaa.thing.md',
  specializations: [],
  is_global: false,
  ...over,
})

/** Three entities across two domains and three types — enough for both axes to differ. */
const ONE = entity({ artifact_id: 'APP@1.a.one', name: 'One', conn_in: 2, conn_out: 1 })
const TWO = entity({
  artifact_id: 'AIF@1.b.two',
  name: 'Two',
  artifact_type: 'application-interface',
  subdomain: 'application-interface',
  conn_in: 0,
  conn_out: 4,
})
const THREE = entity({
  artifact_id: 'REQ@1.c.three',
  name: 'Three',
  artifact_type: 'requirement',
  domain: 'motivation',
  subdomain: 'requirement',
  conn_in: 1,
  conn_out: 0,
})
const POPULATION: EntitySummary[] = [ONE, TWO, THREE]

describe('the first axis: ArchiMate domain', () => {
  it('groups by domain when no domain is being browsed', () => {
    const groups = entityTreemapGroups(POPULATION, '')

    // Two domains in the population, so two groups — not three, which is what grouping by type
    // would give, and the distinction is the whole first axis.
    expect(groups).toHaveLength(2)
    expect(groups.flatMap((g) => g.children.map((l) => l.key)).sort()).toEqual([
      'AIF@1.b.two', 'APP@1.a.one', 'REQ@1.c.three',
    ])
  })

  it('names each group by its domain rather than by its slug', () => {
    expect(groupModeFor('')).toBe('domain')
    expect(groupNameOf(ONE, 'domain')).not.toBe('application-component')
  })
})

describe('the second axis: entity type', () => {
  it('regroups by entity type once a domain is chosen', () => {
    const groups = entityTreemapGroups(POPULATION.slice(0, 2), 'application')

    // Both entities are in the application domain and differ only by type, so grouping by domain
    // would give one group and grouping by type gives two. That is the assertion the requirement is.
    expect(groups.map((g) => g.name).sort()).toEqual(['application-component', 'application-interface'])
  })

  it('takes the type from the field the backend fills from the entity type', () => {
    expect(groupModeFor('application')).toBe('entity-type')
    expect(groupNameOf(TWO, 'entity-type')).toBe('application-interface')
  })

  it('shows an entity whose path carries no type segment rather than dropping it', () => {
    /* A malformed entity is exactly the one a reader needs to see. An empty group name would collapse
       it into no tile at all, which reads as "nothing is wrong here". */
    const orphan = entity({ artifact_id: 'APP@1.d.four', subdomain: '' })
    expect(groupNameOf(orphan, 'entity-type')).toBe('General')
  })
})

describe('sizing', () => {
  it('weighs an entity by its total connections, both directions', () => {
    const [applicationGroup] = entityTreemapGroups([ONE], '')
    const leaves = applicationGroup?.children ?? []

    expect(leaves).toHaveLength(1)
    expect(leaves[0]?.value).toBe(3)
    expect(leaves[0]?.meta).toBe('3 connections')
  })
})

describe('the note under the treemap', () => {
  it('says which axis is in force, so the two views are distinguishable', () => {
    expect(treemapNote('')).toContain('Grouped by domain.')
    expect(treemapNote('application')).toContain('Grouped by entity type.')
    expect(treemapNote('')).toContain('Sized by total connections.')
  })
})
