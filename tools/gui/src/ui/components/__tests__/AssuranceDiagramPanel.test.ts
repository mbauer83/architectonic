import { describe, expect, it } from 'vitest'
import { buildUcaMatrixRows } from '../AssuranceDiagramPanel.helpers'

describe('assurance diagram selection data', () => {
  // The alias→node-id map used to be rebuilt here from a copy of the renderer's naming rule. It is
  // now published by the renderer in the diagram payload, so there is nothing on this side to test:
  // the contract is asserted where it is produced (tests/diagram_types/test_assurance_puml_alias.py)
  // and consumed as data. See assuranceSvgSelection.test.ts for the consumption.

  it('builds the UCA grid from real concern edges', () => {
    const rows = buildUcaMatrixRows([
      { node_id: 'CA1', node_type: 'control-action', name: 'Brake' },
      {
        node_id: 'U1',
        node_type: 'unsafe-control-action',
        name: 'Brake omitted',
        uca_type: 'not-provided',
      },
    ], [
      { edge_id: 'E1', source_id: 'U1', target_id: 'CA1', conn_type: 'concerns' },
    ])

    expect(rows).toHaveLength(1)
    expect(rows[0]?.controlAction.name).toBe('Brake')
    expect(rows[0]?.cells['not-provided']?.[0]?.node_id).toBe('U1')
  })

  it('does not place a UCA without a concern edge into the wrong row', () => {
    const rows = buildUcaMatrixRows([
      { node_id: 'CA1', node_type: 'control-action', name: 'Brake' },
      { node_id: 'U1', node_type: 'unsafe-control-action', name: 'Orphan' },
    ], [])

    expect(rows[0]?.cells).toEqual({})
  })
})
