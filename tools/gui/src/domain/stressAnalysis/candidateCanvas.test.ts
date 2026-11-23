import { describe, expect, it } from 'vitest'
import { commandsOf, editsOf, operationsOf } from './candidateCanvas'

const SERVICE = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'
const ARTIFACTS = 'PRC@1712870400.0Rz5Ex.promote-artifacts'
const QUEUE = 'DOB@1795000000.Queue01.promotion-queue'
const ACCESS = `${ARTIFACTS}---${SERVICE}@@archimate-access`

describe('a canvas command as a candidate edit', () => {
  it('states what is wanted and never a base', () => {
    expect(editsOf({ op: 'model.element.rename', artifact_id: SERVICE, name: 'Review' }))
      .toEqual([{ op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Review' }])
    expect(editsOf({ op: 'model.element.delete', artifact_id: SERVICE })).toEqual([{ op: 'remove_entity', artifact_id: SERVICE }])
    expect(editsOf({
      op: 'model.element.create', artifact_id: QUEUE, artifact_type: 'data-object', name: 'Queue', group: 'g', summary: '',
    })).toEqual([{ op: 'create_entity', artifact_id: QUEUE, fields: { artifact_type: 'data-object', name: 'Queue', group: 'g' } }])
  })

  it('addresses a relation by its triple, and edits it field by field', () => {
    const relation = { artifact_id: ACCESS, description: 'reads', src_multiplicity: '1', tgt_multiplicity: '' }
    expect(editsOf({ op: 'model.relation.create', ...relation })).toEqual([{
      op: 'add_connection', source_entity: ARTIFACTS, connection_type: 'archimate-access', target_entity: SERVICE,
      fields: { description: 'reads', src_multiplicity: '1' },
    }])
    expect(editsOf({ op: 'model.relation.edit', ...relation }).map((edit) => [edit.field, edit.value]))
      .toEqual([['description', 'reads'], ['src_multiplicity', '1'], ['tgt_multiplicity', '']])
    expect(editsOf({ op: 'model.relation.create', ...relation, artifact_id: 'not a relation' })).toEqual([])
  })
})

describe('a candidate drawn when its canvas opens', () => {
  it('draws what it creates, renames and connects between entities with ids', () => {
    const operations = operationsOf({ changes: { operations: [
      { op: 'create_entity', ref: 'q', artifact_id: QUEUE, fields: { artifact_type: 'data-object', name: 'Queue', group: 'g' } },
      { op: 'edit_entity', artifact_id: SERVICE, field: 'name', value: 'Review', base: { value: 'Old' } },
      { op: 'add_connection', source_entity: ARTIFACTS, connection_type: 'archimate-access', target_entity: SERVICE, fields: {} },
      { op: 'add_connection', source_entity: ARTIFACTS, connection_type: 'archimate-access', target_entity: '$ref:q', fields: {} },
      { op: 'remove_entity', artifact_id: ARTIFACTS, base: { revision: 'r' } },
    ] } })
    expect(commandsOf(operations).map((command) => [command.op, command.artifact_id])).toEqual([
      ['model.element.create', QUEUE], ['model.element.rename', SERVICE], ['model.relation.create', ACCESS],
    ])
  })

  it('reads no operations from a record that holds none', () => {
    expect(operationsOf({})).toEqual([])
    expect(operationsOf({ changes: { operations: 'x' } })).toEqual([])
  })
})
