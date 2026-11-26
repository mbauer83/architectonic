/**
 * The canvas's commands as a candidate's edits, and a candidate's operations as the commands that draw
 * them. The canvas speaks the diagram editor's commands (`model.element.*`, `model.relation.*`); a
 * candidate records each as an edit the server turns into an operation with its base
 * (`POST /api/change-sets/{id}/operations`). Nothing here reads or spells a base or an alias.
 */
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { connectionId, connectionParts, isEntityId, stableEntityId } from '../artifactId'

/** An edit as the candidate records it: what is wanted, never what it replaces. */
export type CandidateEdit = Readonly<Record<string, unknown>>

const stated = (fields: Readonly<Record<string, unknown>>): Record<string, unknown> =>
  Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined && value !== ''))

const address = (artifactId: string) => {
  const parts = connectionParts(artifactId)
  return parts && { source_entity: parts.source, connection_type: parts.type, target_entity: parts.target }
}

/** The edits a canvas command makes to a candidate, in the order they are recorded. */
export const editsOf = (command: CanvasCommand): readonly CandidateEdit[] => {
  switch (command.op) {
    case 'model.element.create':
      return [{
        op: 'create_entity', artifact_id: command.artifact_id,
        fields: stated({
          artifact_type: command.artifact_type, name: command.name, group: command.group, summary: command.summary,
        }),
      }]
    case 'model.element.rename':
      return [{ op: 'edit_entity', artifact_id: command.artifact_id, field: 'name', value: command.name }]
    case 'model.element.edit': {
      const { op: _, artifact_id: id, properties, attribute_types: types, ...fields } = command
      const keyed = (field: string, patch: Readonly<Record<string, string | null>> | undefined) =>
        Object.entries(patch ?? {}).map(([key, value]) => ({ op: 'edit_entity', artifact_id: id, field, key, value }))
      return [
        ...Object.entries(fields).filter(([, value]) => value !== undefined)
          .map(([field, value]) => ({ op: 'edit_entity', artifact_id: id, field, value })),
        ...keyed('properties', properties), ...keyed('attribute_types', types),
      ]
    }
    case 'model.element.delete':
      return [{ op: 'remove_entity', artifact_id: command.artifact_id }]
    case 'model.relation.create': {
      const at = address(command.artifact_id)
      return at ? [{ op: 'add_connection', ...at, fields: stated({
        description: command.description,
        src_multiplicity: command.src_multiplicity, tgt_multiplicity: command.tgt_multiplicity,
      }) }] : []
    }
    case 'model.relation.edit': {
      const at = address(command.artifact_id)
      return at ? (['description', 'src_multiplicity', 'tgt_multiplicity'] as const)
        .map((field) => ({ op: 'edit_connection', ...at, field, value: command[field] })) : []
    }
  }
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '')
const isFields = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const fieldsOf = (operation: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>> =>
  isFields(operation.fields) ? operation.fields : {}

/** A candidate record's operations, as recorded under `changes`. */
type Operation = Readonly<Record<string, unknown>>

export const operationsOf = (record: Readonly<Record<string, unknown>>): readonly Operation[] => {
  const operations = isFields(record.changes) ? record.changes.operations : undefined
  return Array.isArray(operations) ? operations.filter(isFields) : []
}

/** A relation as a candidate states it: its ends as an operation or its composed view names them. */
export interface StatedRelation {
  readonly source_entity: string
  readonly connection_type: string
  readonly target_entity: string
  readonly fields: Readonly<Record<string, unknown>>
}

/** A relation's end named as the picture draws it; undefined where the picture draws no such element. */
export type DrawnEnd = (reference: string) => string | undefined

/**
 * How a picture drawing *drawn* names the ends of a candidate's relations. A candidate's answers name every
 * element by its id (what its stack creates, by the id its create chose), often in the short form; the
 * composer attaches a relation only to an end spelled as the picture draws it, which is the full id. An end
 * the picture does not draw has no name.
 */
export const drawnEnds = (drawn: readonly string[]): DrawnEnd => {
  const ends = new Map(drawn.map((id) => [stableEntityId(id), id] as const))
  return (reference) => (isEntityId(reference) ? ends.get(stableEntityId(reference)) : undefined)
}

/**
 * The command that draws *relation*, its ends named by *drawnAs* (`drawnEnds`); null where an end is not drawn.
 * The one translation of a candidate's relation onto a picture: the canvas it is sketched on (`commandsOf`) and
 * every picture it is read on (`candidateDrawing.drawnCommands`).
 */
export const relationCommand = (relation: StatedRelation, drawnAs: DrawnEnd): CanvasCommand | null => {
  const source = drawnAs(relation.source_entity)
  const target = drawnAs(relation.target_entity)
  return source && target ? {
    op: 'model.relation.create', artifact_id: connectionId(source, relation.connection_type, target),
    description: text(relation.fields.description), src_multiplicity: text(relation.fields.src_multiplicity),
    tgt_multiplicity: text(relation.fields.tgt_multiplicity),
  } : null
}

/** The command that draws an element a candidate creates, by the id chosen for it. */
export const creationCommand = (artifactId: string, fields: Readonly<Record<string, unknown>>): CanvasCommand => ({
  op: 'model.element.create', artifact_id: artifactId, artifact_type: text(fields.artifact_type),
  name: text(fields.name), group: text(fields.group),
})

const statedRelation = (operation: Operation): StatedRelation | null => (operation.op === 'add_connection' ? {
  source_entity: text(operation.source_entity), connection_type: text(operation.connection_type),
  target_entity: text(operation.target_entity), fields: fieldsOf(operation),
} : null)

/**
 * The commands that draw a candidate's own operations on its canvas when it is opened over a picture drawing
 * *drawn*: what it creates (by the id chosen for it), what it renames, and the relations it adds, each end
 * named as the canvas draws it (`drawnEnds`).
 */
export const commandsOf = (operations: readonly Operation[], drawn: readonly string[]): readonly CanvasCommand[] => {
  const creates = operations.flatMap((operation) => (
    operation.op === 'create_entity' && typeof operation.artifact_id === 'string'
      ? [creationCommand(operation.artifact_id, fieldsOf(operation))] : []))
  const renames = operations.flatMap((operation): CanvasCommand[] => (
    operation.op === 'edit_entity' && operation.field === 'name' && typeof operation.artifact_id === 'string'
      ? [{ op: 'model.element.rename', artifact_id: operation.artifact_id, name: text(operation.value) }] : []))
  const drawnAs = drawnEnds([...drawn, ...creates.map((one) => one.artifact_id)])
  const relations = operations.flatMap((operation) => {
    const relation = statedRelation(operation)
    const command = relation && relationCommand(relation, drawnAs)
    return command ? [command] : []
  })
  return [...creates, ...renames, ...relations]
}
