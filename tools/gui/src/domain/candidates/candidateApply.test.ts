import { describe, expect, it } from 'vitest'
import type { OperationStanding } from '../schemas/candidates'
import {
  applyPreview, appliedValues, canApply, editedValues, operationLabel, operationsAppliedValues, previewSentence,
} from './candidateApply'

const standing = (position: string, operation: Record<string, unknown> = { op: 'edit_entity' }): OperationStanding =>
  ({ operation, standing: position, reason: position })

const answered = (positions: string[], refusal?: string) => ({
  candidate: 'CAND-1', dry_run: true, integrated: false, standing: positions.map((one) => standing(one)),
  ...(refusal ? { refusal } : {}),
})

describe('applyPreview', () => {
  it('writes what applies and skips what the model already holds', () => {
    const preview = applyPreview(answered(['applies', 'already-there', 'applies']))
    expect(preview.writes).toHaveLength(2)
    expect(preview.skipped).toHaveLength(1)
    expect(preview.refusal).toBeNull()
    expect(canApply(preview)).toBe(true)
    expect(previewSentence(preview)).toBe(
      'Writes 2 operations to the model in one write. Skips 1 operation the model already holds.',
    )
  })

  it('cannot be confirmed while the server refuses it, in the server\'s words', () => {
    const preview = applyPreview(answered(['drifted'], 'CAND-1 cannot be applied until it is re-based.'))
    expect(preview.refusal).toBe('CAND-1 cannot be applied until it is re-based.')
    expect(canApply(preview)).toBe(false)
  })

  it('cannot be confirmed with no operations at all', () => {
    const preview = applyPreview(answered([]))
    expect(canApply(preview)).toBe(false)
    expect(previewSentence(preview)).toBe('Writes nothing to the model.')
  })
})

describe('operationLabel', () => {
  const link = { source_entity: 'APP@1.a', connection_type: 'serving', target_entity: 'APP@1.b' }
  it.each([
    [{ op: 'create_entity', fields: { name: 'Queue' } }, 'Create Queue'],
    [{ op: 'edit_entity', artifact_id: 'APP@1.a', field: 'properties', key: 'tier' }, 'Set properties.tier of APP@1.a'],
    [{ op: 'remove_entity', artifact_id: 'APP@1.a' }, 'Remove APP@1.a'],
    [{ op: 'add_connection', ...link }, 'Connect APP@1.a → APP@1.b (serving)'],
    [{ op: 'edit_connection', ...link, field: 'description' }, 'Set description of APP@1.a → APP@1.b (serving)'],
    [{ op: 'remove_connection', ...link }, 'Disconnect APP@1.a → APP@1.b (serving)'],
    [{ op: 'unknown' }, 'unknown'],
  ])('names %j as %s', (operation, label) => {
    expect(operationLabel(operation)).toBe(label)
  })
})

describe('editedValues', () => {
  it('reads an edit as the value its base was written over and the value it writes', () => {
    expect(editedValues({ op: 'edit_entity', field: 'summary', value: 'new text', base: { value: 'old text' } }))
      .toEqual({ before: 'old text', after: 'new text' })
    expect(editedValues({ op: 'edit_connection', field: 'name', value: 'b', base: { value: null } }))
      .toEqual({ before: null, after: 'b' })
  })

  it('reads nothing from another operation, or from an edit based on a revision', () => {
    expect(editedValues({ op: 'create_entity', fields: { name: 'x' } })).toBeNull()
    expect(editedValues({ op: 'remove_entity', base: { revision: 'r1' } })).toBeNull()
    expect(editedValues({ op: 'edit_entity', value: 'x', base: { revision: 'r1' } })).toBeNull()
  })
})

describe('appliedValues', () => {
  const edit = { op: 'edit_entity', field: 'summary', value: 'new text', base: { revision: 'r1' } }

  it('reads what applying an edit replaces from what the model holds where it writes', () => {
    expect(appliedValues({ operation: edit, standing: 'applies', reason: '', holds: 'text now' }))
      .toEqual({ before: 'text now', after: 'new text' })
  })

  it('reads a held null as "the model holds nothing there", not as "not read"', () => {
    const named = { ...edit, base: { value: 'old text' } }
    expect(appliedValues({ operation: named, standing: 'applies', reason: '', holds: null }))
      .toEqual({ before: null, after: 'new text' })
  })

  it('falls back to the value the edit was written over where the model was not read', () => {
    const named = { ...edit, base: { value: 'old text' } }
    expect(appliedValues({ operation: named, standing: 'drifted', reason: '' })).toEqual({ before: 'old text', after: 'new text' })
    expect(appliedValues({ operation: edit, standing: 'applies', reason: '' })).toBeNull()
  })

  it('reads nothing for an operation that is not an edit', () => {
    expect(appliedValues({ operation: { op: 'create_entity' }, standing: 'applies', reason: '', holds: 'x' })).toBeNull()
  })
})

describe('operationsAppliedValues', () => {
  const edit = { op: 'edit_entity', artifact_id: 'SRV@1.a', field: 'summary', value: 'new text', base: { revision: 'r1' } }
  const keyed = { op: 'edit_entity', artifact_id: 'SRV@1.a', field: 'properties', key: 'tier', value: 'gold', base: { revision: 'r1' } }
  const relation = {
    op: 'edit_connection', source_entity: 'SRV@1.a', connection_type: 'archimate-serving', target_entity: 'APP@1.b',
    field: 'description', value: 'serves it', base: { revision: 'r2' },
  }

  it('reads each edit of a dry run against the standing answered for what it writes, in any order', () => {
    const standing: OperationStanding[] = [
      { operation: relation, standing: 'applies', reason: '', holds: 'served' },
      { operation: keyed, standing: 'applies', reason: '', holds: 'silver' },
      { operation: edit, standing: 'applies', reason: '', holds: 'text now' },
    ]
    expect(operationsAppliedValues([edit, { op: 'remove_entity', artifact_id: 'X@1.c' }, keyed, relation], standing))
      .toEqual([
        { before: 'text now', after: 'new text' }, null, { before: 'silver', after: 'gold' },
        { before: 'served', after: 'serves it' },
      ])
  })

  it('reads an edit with no standing as the edit alone reads it', () => {
    expect(operationsAppliedValues([edit, { ...edit, base: { value: 'old text' } }], [])).toEqual([
      null, { before: 'old text', after: 'new text' },
    ])
  })
})
