/**
 * The rows of what Save would write name a relation's type as the picture draws it: `serving`, not the
 * catalogue's `archimate-serving` and not a hand-spelt "archimate serving".
 */
import { describe, expect, it } from 'vitest'
import { contentChanges } from '../sessionChanges'

const named = (key: string) => ({ 'APP@1.a': 'Portal', 'APP@3.c': 'Ledger' })[key] ?? key

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
})
