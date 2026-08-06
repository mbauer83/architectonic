import type { AuthoredGrouping } from '../domain/authoredGrouping'

/**
 * What a diagram *draws* — everything that ends up in the picture, and nothing about the operation.
 *
 * Shared by preview and by both writes, because all three render the same diagram. Preview once kept
 * its own copy of this list and fell behind it: groupings reached the writes and never the preview,
 * so the picture shown was not the picture saved.
 */
export type DiagramComposition = {
  diagram_type: string; name: string;
  entity_ids: string[]; connection_ids: string[];
  diagram_entities?: Record<string, unknown>;
  authored_groupings?: readonly AuthoredGrouping[];
}

/** A composition, plus what the write itself decides. */
export type DiagramWriteBody = DiagramComposition & {
  version?: string; status?: string;
  viewpoint?: { slug: string; version: number; enforcement_override?: 'off' | 'warn' | 'ghost' } | null;
  dry_run?: boolean;
}
