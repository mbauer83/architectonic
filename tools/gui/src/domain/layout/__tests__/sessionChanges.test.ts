/**
 * The rows of what Save would write name a relation's type as the picture draws it: `serving`, not the
 * catalogue's `archimate-serving` and not a hand-spelt "archimate serving".
 */
import { describe, expect, it } from 'vitest'
import { contentChanges } from '../sessionChanges'
import { stableEntityId } from '../../artifactId'

const named = (key: string) => ({ 'APP@1.a': 'Portal', 'APP@3.c': 'Ledger' })[stableEntityId(key)] ?? key

describe('the rows of a session', () => {
  it('name a relation by its ends and the type the picture draws', () => {
    const rows = contentChanges(
      {
        drawnRelations: ['APP@1.a---APP@3.c@@archimate-access'],
        commands: [{
          op: 'model.relation.create', artifact_id: 'APP@1.a---APP@3.c@@archimate-serving',
          description: '', src_multiplicity: '', tgt_multiplicity: '',
        }],
      },
      new Set(), named, named, (grouping) => grouping,
    )
    expect(rows.map((row) => row.text)).toEqual([
      'Drawn from the model: Portal — access → Ledger',
      'Create relationship: Portal — serving → Ledger',
    ])
  })

  it('name a label typed on a relation once, with its last text, unless it came with a relation change', () => {
    const rows = contentChanges(
      {
        overlays: [
          { artifact_id: 'APP@1.a---APP@3.c@@archimate-flow', label: 'orders' },
          { artifact_id: 'APP@1.a.portal---APP@3.c@@archimate-flow', label: 'orders, daily' },
          { artifact_id: 'APP@3.c---APP@1.a@@archimate-access', label: '' },
          { artifact_id: 'APP@1.a---APP@3.c@@archimate-serving', label: 'drawn with it' },
        ],
        drawnRelations: ['APP@1.a---APP@3.c@@archimate-serving'],
      },
      new Set(), named, named, (grouping) => grouping,
    )
    expect(rows.map((row) => row.text)).toEqual([
      'Drawn from the model: Portal — serving → Ledger',
      'Label on this diagram: Portal — flow → Ledger — “orders, daily”',
      'Label taken off this diagram: Ledger — access → Portal',
    ])
  })
})
