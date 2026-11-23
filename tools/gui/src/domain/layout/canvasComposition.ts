/** The unsaved drawing and the diagram replacement derived from one canvas session. */
import type {
  CanvasCommand,
  DiagramComposition,
  GeometryComposition,
} from '../../ports/diagramWriteBodies'
import { membershipWithout } from './diagramMembership'
import type { DrawnMembership } from './diagramMembership'
import { stableEntityId } from '../artifactId'

interface Content {
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
  const links = commands.filter(
    (c): c is Extract<CanvasCommand, { src_multiplicity: string }> => c.op === 'model.relation.create',
  )
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
  const entities = { ...drawn.diagram_entities }
  if (state.overlays?.length) {
    const prior = Array.isArray(entities._connections) ? entities._connections : []
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
    proposed_relations: links
      .filter((c) => write.connection_ids.includes(c.artifact_id))
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
