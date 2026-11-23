/**
 * What a reading reports beyond the picture: the relations the model has for the selection that this
 * diagram does not draw, and the relationships the model derives through intermediate elements.
 *
 * The picture can only light what it draws, so these two are lists. Both follow the reach's direction:
 * a list of what leads to the selection is shown only while incoming reach is on, and likewise outgoing.
 * A relation whose type has no direction leads both ways, so it is shown while either is on.
 */
import type { Reach } from './diagramReading'

/** Which way a relation runs relative to the selection; `undirected` for a type with no direction. */
export type Way = 'incoming' | 'outgoing' | 'undirected'

/** Whether the reach shows a relation running *way*. */
export const reachShows = (reach: Reach, way: Way): boolean =>
  way === 'incoming' ? reach.incoming !== 0
    : way === 'outgoing' ? reach.outgoing !== 0
      : reach.incoming !== 0 || reach.outgoing !== 0

/** An element the reading reaches on the picture, as the panel lists it. */
export interface ReachedRow {
  readonly id: string
  readonly name: string
  readonly type: string
  readonly domain: string
}

/** A model relation as the diagram's context reports it. */
export interface ModelRelation {
  readonly artifact_id: string
  readonly source: string
  readonly target: string
  readonly source_name: string
  readonly target_name: string
  readonly conn_type: string
}

/** A relation the model has for the selection and this diagram does not draw. */
export interface NotDrawnRow {
  readonly id: string
  /** The selected end, which the picture draws. */
  readonly here: string
  readonly other: string
  readonly otherName: string
  /** Whether the other end is drawn on this diagram, though the relation is not. */
  readonly otherDrawn: boolean
  readonly type: string
  readonly way: Way
}

/** The model's relations for *selection* that are not drawn, one step out, as far as *reach* shows. */
export const notDrawnOf = (input: {
  selection: readonly string[]
  candidates: readonly ModelRelation[]
  drawnRelations: ReadonlySet<string>
  drawnEntities: ReadonlySet<string>
  undirected: ReadonlySet<string>
  reach: Reach
}): NotDrawnRow[] => {
  const selected = new Set(input.selection)
  return input.candidates.flatMap((relation): NotDrawnRow[] => {
    if (input.drawnRelations.has(relation.artifact_id)) return []
    const fromHere = selected.has(relation.source)
    if (!fromHere && !selected.has(relation.target)) return []
    const way: Way = input.undirected.has(relation.conn_type) ? 'undirected' : fromHere ? 'outgoing' : 'incoming'
    if (!reachShows(input.reach, way)) return []
    const other = fromHere ? relation.target : relation.source
    return [{
      id: relation.artifact_id, here: fromHere ? relation.source : relation.target, other,
      otherName: fromHere ? relation.target_name : relation.source_name, otherDrawn: input.drawnEntities.has(other),
      type: relation.conn_type, way,
    }]
  })
}

/** A relationship the derivation composed from one selected element, as the server reports it. */
export interface DerivedFrom {
  readonly entity_id: string
  readonly entity_name: string
  readonly type: string
  readonly direction: 'outbound' | 'inbound'
  readonly certainty: string
  readonly hops: number
}

export interface DerivedRow {
  readonly entityId: string
  readonly name: string
  readonly type: string
  readonly way: Way
  readonly hops: number
}

/**
 * The derived relationships of every selected element, split by certainty: the shortest of each
 * (end, type, way), none to another selected element, nearest first. A derived relationship of a type
 * with no direction runs neither way, whichever end the derivation started from.
 */
export const derivedOf = (
  bySelected: ReadonlyMap<string, readonly DerivedFrom[]>, reach: Reach, undirected: ReadonlySet<string>,
): { certain: DerivedRow[]; potential: DerivedRow[] } => {
  const best = new Map<string, DerivedRow & { certain: boolean }>()
  for (const rows of bySelected.values()) {
    for (const row of rows) {
      const way: Way = undirected.has(row.type) ? 'undirected' : row.direction === 'outbound' ? 'outgoing' : 'incoming'
      if (bySelected.has(row.entity_id) || !reachShows(reach, way)) continue
      const key = `${row.entity_id}|${row.type}|${way}`
      const held = best.get(key)
      const certain = row.certainty === 'certain'
      if (held && (held.certain && !certain || held.certain === certain && held.hops <= row.hops)) continue
      best.set(key, { entityId: row.entity_id, name: row.entity_name, type: row.type, way, hops: row.hops, certain })
    }
  }
  const sorted = [...best.values()].sort((a, b) => a.hops - b.hops || a.name.localeCompare(b.name))
  const strip = ({ certain: _certain, ...row }: DerivedRow & { certain: boolean }): DerivedRow => row
  return {
    certain: sorted.filter((row) => row.certain).map(strip),
    potential: sorted.filter((row) => !row.certain).map(strip),
  }
}
