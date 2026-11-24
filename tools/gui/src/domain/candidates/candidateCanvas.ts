/**
 * The canvas's commands as a candidate's edits, and a candidate's operations as the commands that draw
 * them. The canvas speaks the diagram editor's commands (`model.element.*`, `model.relation.*`); a
 * candidate records each as an edit the server turns into an operation with its base
 * (`POST /api/change-sets/{id}/operations`). Nothing here reads or spells a base or an alias.
 */
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import type { ScopedEntity } from '../schemas/candidates'
import { connectionId, connectionParts, isEntityId } from '../artifactId'

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

/**
 * The ids chosen for what a candidate's stack creates, by the reference its composed view names each
 * with. The server spells the reference; this only looks it up.
 */
export const chosenIds = (view: { readonly entities: readonly ScopedEntity[] }): ReadonlyMap<string, string> =>
  new Map(view.entities.flatMap((one) => (one.artifact_id ? [[one.id, one.artifact_id] as const] : [])))

/**
 * The commands that draw a candidate's own operations on its canvas when it is opened: what it
 * creates (by the id chosen for it), what it renames, and the relations it adds. A relation's end that
 * names something the stack creates is a reference the server keeps; *chosen* (the composed view's
 * `chosenIds`) resolves it to the id the canvas drew that element with.
 */
export const commandsOf = (
  operations: readonly Readonly<Record<string, unknown>>[], chosen: ReadonlyMap<string, string> = new Map(),
): readonly CanvasCommand[] =>
  operations.flatMap((operation): CanvasCommand[] => {
    const fields = fieldsOf(operation)
    if (operation.op === 'create_entity' && typeof operation.artifact_id === 'string') {
      return [{
        op: 'model.element.create', artifact_id: operation.artifact_id, artifact_type: text(fields.artifact_type),
        name: text(fields.name), group: text(fields.group),
      }]
    }
    if (operation.op === 'edit_entity' && operation.field === 'name' && typeof operation.artifact_id === 'string') {
      return [{ op: 'model.element.rename', artifact_id: operation.artifact_id, name: text(operation.value) }]
    }
    const source = chosen.get(text(operation.source_entity)) ?? text(operation.source_entity)
    const target = chosen.get(text(operation.target_entity)) ?? text(operation.target_entity)
    if (operation.op === 'add_connection' && isEntityId(source) && isEntityId(target)) {
      return [{
        op: 'model.relation.create', artifact_id: connectionId(source, text(operation.connection_type), target),
        description: text(fields.description), src_multiplicity: text(fields.src_multiplicity),
        tgt_multiplicity: text(fields.tgt_multiplicity),
      }]
    }
    return []
  })
