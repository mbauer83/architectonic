/** The unsaved drawing and the diagram replacement derived from one canvas session. */
import type {
  CanvasCommand,
  GroupingIntent,
  DiagramComposition,
  GeometryComposition,
} from '../../ports/diagramWriteBodies'
import { membershipWithout } from './diagramMembership'
import type { DrawnMembership } from './diagramMembership'
import { connectionParts, stableConnectionId, stableEntityId } from '../artifactId'

import type { DiagramContext, EntityDetail } from '..'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import { isRecord } from '../records'
import { type ArchimateOccurrence, occurrenceItems } from '../archimateOccurrences'


interface Content {
  readonly regroupings?: readonly GroupingIntent[]
  /** Further drawings of elements the diagram already draws, added in this session. */
  readonly occurrences?: readonly ArchimateOccurrence[]
  readonly addedTypes?: ReadonlyMap<string, string>
  readonly additions?: ReadonlyMap<string, string>
  readonly commands?: readonly CanvasCommand[]
  readonly overlays?: readonly Record<string, unknown>[]
}

export function composeCanvas(drawn: DrawnMembership, state: Content, removed: ReadonlySet<string>) {
  const commands = state.commands ?? []
  const deletions = new Set([
    ...removed,
    ...commands.filter((c) => c.op === 'model.element.delete').map((c) => c.artifact_id),
  ])
  const creates = commands.filter((c) => c.op === 'model.element.create')
  const relations = commands.filter(
    (c): c is Extract<CanvasCommand, { src_multiplicity: string }> => 'src_multiplicity' in c,
  )
  const links = relations.filter(c => c.op === 'model.relation.create')
  const kept = membershipWithout(
    {
      ...drawn,
      entity_ids: [
        ...drawn.entity_ids,
        ...(state.additions?.keys() ?? []),
        ...creates.map((c) => c.artifact_id),
      ],
      connection_ids: [...drawn.connection_ids, ...links.map((c) => c.artifact_id)],
    },
    deletions,
  )
  const entities: Record<string, unknown> = { ...drawn.diagram_entities }
  // A further drawing removed, or of an element deleted, goes from the statements; one added here joins them.
  const gone = new Set([...deletions].map(stableEntityId))
  const occurrences = [...occurrenceItems(entities), ...state.occurrences ?? []]
    .filter((one) => !removed.has(one.id) && !gone.has(stableEntityId(one.backing_entity_id)))
  if (occurrences.length || 'occurrence' in entities) entities.occurrence = occurrences
  if (state.overlays?.length) {
    const stored: unknown = entities._connections
    const prior = Array.isArray(stored) ? (stored as unknown[]).filter(isRecord) : []
    const overrides = new Map(state.overlays.map((row) => [row.artifact_id, row]))
    entities._connections = [
      ...prior.map((row) => {
        const update = overrides.get(row.artifact_id ?? row.connection_id)
        if (!update) return row
        overrides.delete(update.artifact_id)
        return { ...row, ...update }
      }),
      ...overrides.values(),
    ]
  }
  const write: DiagramComposition = {
    name: drawn.name,
    diagram_type: drawn.diagram_type,
    entity_ids: [...kept.entity_ids],
    connection_ids: [...kept.connection_ids],
    ...(Object.keys(entities).length ? { diagram_entities: entities } : {}),
    ...(kept.authored_groupings ? { authored_groupings: kept.authored_groupings } : {}),
    ...(state.regroupings?.length ? { grouping_intents: state.regroupings } : {}),
  }
  const renames = Object.fromEntries(
    commands
      .filter((c) => c.op === 'model.element.rename')
      .map((c) => [stableEntityId(c.artifact_id), c.name]),
  )
  const preview: GeometryComposition = {
    ...write,
    entity_ids: write.entity_ids.filter((id) => !creates.some((c) => c.artifact_id === id)),
    connection_ids: write.connection_ids.filter((id) => !links.some((c) => c.artifact_id === id)),
    proposed_elements: creates
      .filter((c) => write.entity_ids.includes(c.artifact_id))
      .map((c) => ({
        artifact_id: c.artifact_id,
        name: c.name,
        specializations: c.specializations,
        attributes: c.attributes,
      })),
    proposed_relations: relations
      .filter(c => write.connection_ids.some(id => stableConnectionId(id) === stableConnectionId(c.artifact_id)))
      .map((c) => ({
        artifact_id: c.artifact_id,
        description: c.description,
        src_multiplicity: c.src_multiplicity,
        tgt_multiplicity: c.tgt_multiplicity,
      })),
    ...(Object.keys(renames).length
      ? {
          diagram_entities: {
            ...entities,
            display_labels: {
              ...renames,
              ...(typeof entities.display_labels === 'object' ? entities.display_labels : {}),
            },
          },
        }
      : {}),
  }
  return { preview, write }
}

/**
 * *commands* with *command* kept: a rename or a relation edit replaces the one before it for the same
 * artifact; an element's details merge over the ones before them, key by key for a keyed field, as the
 * write path applies successive edits — so a second edit that left a field alone does not drop the first.
 */
export const withCommand = (commands: readonly CanvasCommand[], command: CanvasCommand): CanvasCommand[] => {
  const same = (one: CanvasCommand) => one.op === command.op && one.artifact_id === command.artifact_id
  if (command.op === 'model.element.edit') {
    const before = commands.find(same)
    const merged = before?.op === 'model.element.edit' ? {
      ...before, ...command,
      ...(before.properties || command.properties
        ? { properties: { ...before.properties, ...command.properties } } : {}),
      ...(before.attribute_types || command.attribute_types
        ? { attribute_types: { ...before.attribute_types, ...command.attribute_types } } : {}),
    } : command
    return [...commands.filter((one) => !same(one)), merged]
  }
  const replaces = command.op === 'model.element.rename' || command.op === 'model.relation.edit'
  return [...(replaces ? commands.filter((one) => !same(one)) : commands), command]
}

/**
 * *content* without the draft *id*, as though it had never been created: its creation, and everything
 * the session proposed about it — a rename, details, a relation from or to it, a move into a box.
 */
export const withoutDraft = <C extends Content>(content: C, id: string): C => {
  const own = stableEntityId(id)
  const about = (command: CanvasCommand): boolean => {
    const ends = connectionParts(command.artifact_id)
    return ends ? [ends.source, ends.target].some((end) => stableEntityId(end) === own)
      : stableEntityId(command.artifact_id) === own
  }
  const regroupings = (content.regroupings ?? [])
    .map((intent) => ({ ...intent, keys: intent.keys.filter((key) => stableEntityId(key) !== own) }))
    .filter((intent) => intent.keys.length > 0)
  return { ...content, commands: (content.commands ?? []).filter((one) => !about(one)), regroupings }
}

/**
 * *detail* as the session would leave it: its last pending rename, and its pending details over what the
 * model holds — what the entity form opens on when an element's details are edited a second time.
 */
export const withPendingDetails = (detail: EntityDetail, commands: readonly CanvasCommand[]): EntityDetail => {
  const own = commands.filter((one) => stableEntityId(one.artifact_id) === stableEntityId(detail.artifact_id))
  const renamed = own.filter((one) => one.op === 'model.element.rename').at(-1)
  const edit = own.find((one) => one.op === 'model.element.edit')
  if (!renamed && !edit) return detail
  const properties = { ...detail.properties }
  for (const [key, value] of Object.entries(edit?.properties ?? {})) {
    if (value === null) delete properties[key]
    else properties[key] = value
  }
  return {
    ...detail,
    ...(renamed ? { name: renamed.name } : {}),
    ...(edit ? {
      summary: edit.summary ?? detail.summary, notes: edit.notes ?? detail.notes,
      status: edit.status ?? detail.status, group: edit.group ?? detail.group,
      keywords: edit.keywords ?? detail.keywords, specializations: edit.specializations ?? detail.specializations,
      properties,
    } : {}),
  }
}

/** Resolve drawing aliases to their model identity, including unsaved additions and renames. */
export function canvasMembers(context: DiagramContext, state: Content | null, picture: LayoutGeometry | null) {
  const lookup = new Map(
    [...context.entities, ...context.suggested_entities.flatMap((s) => s.items)].map((e) => [
      stableEntityId(e.artifact_id),
      { id: e.artifact_id, name: e.name, type: e.artifact_type },
    ]),
  )
  for (const [id, name] of state?.additions ?? []) {
    const key = stableEntityId(id)
    if (!lookup.has(key)) lookup.set(key, { id, name, type: state?.addedTypes?.get(id) ?? '' })
  }
  const cmds = state?.commands ?? []
  for (const c of cmds) {
    if (c.op === 'model.element.create')
      lookup.set(stableEntityId(c.artifact_id), {
        id: c.artifact_id,
        name: c.name,
        type: c.artifact_type ?? '',
      })
    if (c.op === 'model.element.rename') {
      const m = lookup.get(stableEntityId(c.artifact_id))
      if (m) m.name = c.name
    }
  }
  // A further drawing is the element it draws again: the same id, name and type, under its own alias.
  const backing = new Map([...occurrenceItems(context.diagram.diagram_entities ?? {}), ...state?.occurrences ?? []]
    .map((one) => [one.id, stableEntityId(one.backing_entity_id)]))
  return [...(picture?.elements ?? []), ...(picture?.boxes ?? [])].flatMap((s) => {
    const item = lookup.get(s.key ?? '') ?? lookup.get(backing.get(s.key ?? '') ?? '')
    return item ? [{ ...item, alias: s.alias }] : []
  })
}

/** The status a draft has: an element the model holds provisionally, as everything a canvas creates is. */
export const DRAFT_STATUS = 'draft'

/**
 * The shapes of *picture* that draw a draft (sketch 03·4, D19): an element the model holds as a draft,
 * or one this session creates, which is written as one — however often it is drawn. By alias.
 */
export function draftAliases(context: DiagramContext, state: Content | null, picture: LayoutGeometry | null) {
  const drafts = new Set([
    ...context.entities.filter((one) => one.status === DRAFT_STATUS).map((one) => stableEntityId(one.artifact_id)),
    ...(state?.commands ?? []).filter((c) => c.op === 'model.element.create').map((c) => stableEntityId(c.artifact_id)),
  ])
  return new Set(canvasMembers(context, state, picture)
    .filter((one) => drafts.has(stableEntityId(one.id))).map((one) => one.alias))
}
