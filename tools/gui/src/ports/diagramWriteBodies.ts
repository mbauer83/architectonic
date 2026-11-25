import type { AuthoredGrouping } from '../domain/authoredGrouping'
import type { LayoutPatch } from './DiagramLayoutRepository'

/**
 * What a diagram *draws* — everything that ends up in the picture, and nothing about the operation.
 *
 * Shared by preview and by both writes, because all three render the same diagram. Preview once kept
 * its own copy of this list and fell behind it: groupings reached the writes and never the preview,
 * so the picture shown was not the picture saved.
 */
export type DiagramComposition = {
  diagram_type: string
  name: string
  entity_ids: string[]
  connection_ids: string[]
  diagram_entities?: Record<string, unknown>
  authored_groupings?: readonly AuthoredGrouping[]
  /** Moves into and out of the diagram's own boxes, applied to `authored_groupings` as the body is read. */
  grouping_intents?: readonly GroupingIntent[]
}

/**
 * Moving instances into one of the diagram's own boxes (`nest`, by grouping id) or out of the box they
 * are in (`unnest`), as the arrange route spells them; the server compiles them (`grouping_intents.py`).
 */
export type GroupingIntent =
  | { readonly intent: 'nest'; readonly keys: readonly string[]; readonly grouping: string }
  | { readonly intent: 'unnest'; readonly keys: readonly string[] }

/** A composition, plus what the write itself decides. */
export type DiagramWriteBody = DiagramComposition & {
  version?: string
  status?: string
  /**
   * The model-project collection the diagram is filed in — its home. Not part of the composition:
   * where a diagram lives is not something it draws, and `DiagramComposition` carries only what
   * ends up in the picture. On a replacement, omitting it leaves the diagram where it is.
   */
  group?: string
  viewpoint?: { slug: string; version: number; enforcement_override?: 'off' | 'warn' | 'ghost' } | null
  dry_run?: boolean
}

/**
 * A replacement of a diagram: a write body, and the layout as a patch against what was read — written in
 * the same write as the membership and pruned to what the diagram then holds, so the stored layout
 * matches the body. Only a replacement takes one: a new diagram has no layout to patch.
 */
export type CanvasCommand =
  | {
      op: 'model.element.create'
      artifact_type: string
      artifact_id: string
      name: string
      group: string
      specializations?: string[]
      summary?: string
      attributes?: Record<string, string>
    }
  | { op: 'model.element.rename'; artifact_id: string; name: string }
  | ({ op: 'model.element.edit'; artifact_id: string } & ElementDetailsEdit)
  | { op: 'model.element.delete'; artifact_id: string }
  | {
      op: 'model.relation.create' | 'model.relation.edit'
      artifact_id: string
      description: string
      src_multiplicity: string
      tgt_multiplicity: string
    }

/**
 * An element's details as its entity form edits them, kept in a canvas session until Save: the fields
 * `editEntity` takes, an omitted one left as it is; `properties` and `attribute_types` patch key by key.
 */
export interface ElementDetailsEdit {
  summary?: string
  notes?: string
  status?: string
  group?: string
  keywords?: string[]
  specializations?: string[]
  properties?: Record<string, string | null>
  attribute_types?: Record<string, string | null>
}

export type DiagramReplaceBody = DiagramWriteBody & {
  /** false gives a hand-written body up: generated from the composition from then on, and arrangeable. */
  manual_layout?: boolean
  layout_patch?: LayoutPatch
  commands?: readonly CanvasCommand[]
}
export type GeometryComposition = DiagramComposition & {
  arrangement?: import('../domain/layout/arrangementLayout').ArrangedLayout
  proposed_elements?: {
    artifact_id: string
    name: string
    specializations?: string[]
    attributes?: Record<string, string>
  }[]
  proposed_relations?: {
    artifact_id: string
    description: string
    src_multiplicity: string
    tgt_multiplicity: string
  }[]
}
