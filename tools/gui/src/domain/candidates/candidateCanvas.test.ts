import { describe, expect, it } from 'vitest'
import { commandsOf, editsOf, operationsOf } from './candidateCanvas'
import { drawnCommands } from './candidateDrawing'

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

  it('edits an element\'s details field by field, and a keyed field key by key', () => {
    expect(editsOf({
      op: 'model.element.edit', artifact_id: SERVICE, summary: 'Serves', keywords: ['a'],
      properties: { owner: 'Ops', retired: null },
    })).toEqual([
      { op: 'edit_entity', artifact_id: SERVICE, field: 'summary', value: 'Serves' },
      { op: 'edit_entity', artifact_id: SERVICE, field: 'keywords', value: ['a'] },
      { op: 'edit_entity', artifact_id: SERVICE, field: 'properties', key: 'owner', value: 'Ops' },
      { op: 'edit_entity', artifact_id: SERVICE, field: 'properties', key: 'retired', value: null },
    ])
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
      { op: 'add_connection', source_entity: ARTIFACTS, connection_type: 'archimate-access', target_entity: '$ref:p', fields: {} },
      { op: 'remove_entity', artifact_id: ARTIFACTS, base: { revision: 'r' } },
    ] } })
    const commands = commandsOf(operations, [SERVICE, ARTIFACTS])
    expect(commands.map((command) => [command.op, command.artifact_id])).toEqual([
      ['model.element.create', QUEUE], ['model.element.rename', SERVICE], ['model.relation.create', ACCESS],
    ])
  })

  it('names a relation\'s end as the canvas draws it, where its operation named the element by its short id', () => {
    const operations = operationsOf({ changes: { operations: [
      { op: 'create_entity', ref: 'q', artifact_id: QUEUE, fields: { artifact_type: 'data-object', name: 'Queue', group: 'g' } },
      { op: 'add_connection', source_entity: 'DOB@1795000000.Queue01', connection_type: 'archimate-serving',
        target_entity: 'SRV@1712870400.Uv9Wx9', fields: {} },
    ] } })
    expect(commandsOf(operations, [SERVICE]).map((command) => command.artifact_id)).toEqual([
      QUEUE, `${QUEUE}---${SERVICE}@@archimate-serving`,
    ])
    // An end the canvas does not draw is not one the composer could attach: no relation is drawn to it.
    expect(commandsOf(operations, []).map((command) => command.op)).toEqual(['model.element.create'])
  })

  it('draws a relation exactly as every picture a candidate is read on draws it', () => {
    const operation = { op: 'add_connection', source_entity: 'DOB@1795000000.Queue01', connection_type: 'archimate-serving',
      target_entity: 'SRV@1712870400.Uv9Wx9', fields: { description: 'feeds', src_multiplicity: '1' } }
    const view = {
      entities: [{ id: 'DOB@1795000000.Queue01', artifact_id: QUEUE, fields: { name: 'Queue', artifact_type: 'data-object', group: 'g' } }],
      connections: [{ ...operation, fields: { ...operation.fields } }],
    }
    const sketched = commandsOf([
      { op: 'create_entity', ref: 'q', artifact_id: QUEUE, fields: { artifact_type: 'data-object', name: 'Queue', group: 'g' } },
      operation,
    ], [SERVICE])
    const read = drawnCommands(view, { entities: [{ artifact_id: SERVICE, name: 'Service' }], connections: [], undrawn: [] })

    expect(sketched).toEqual(read)
    expect(sketched.find((command) => command.op === 'model.relation.create')?.artifact_id)
      .toBe(`${QUEUE}---${SERVICE}@@archimate-serving`)
  })

  it('redraws a relation to what the candidate created, named by the stable form of the id its create chose', () => {
    const operations = operationsOf({ changes: { operations: [
      { op: 'create_entity', ref: 'q', artifact_id: QUEUE, fields: { artifact_type: 'data-object', name: 'Queue', group: 'g' } },
      { op: 'add_connection', source_entity: ARTIFACTS, connection_type: 'archimate-access', target_entity: 'DOB@1795000000.Queue01', fields: {} },
    ] } })

    expect(commandsOf(operations, [ARTIFACTS]).map((command) => command.artifact_id)).toEqual([
      QUEUE, `${ARTIFACTS}---${QUEUE}@@archimate-access`,
    ])
  })

  it('reads no operations from a record that holds none', () => {
    expect(operationsOf({})).toEqual([])
    expect(operationsOf({ changes: { operations: 'x' } })).toEqual([])
  })
})
