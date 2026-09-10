import type { GroupEntry } from '../../domain/schemas/groups'
import { type CollectionAxis, filableCollections } from '../lib/collectionAxes'

/**
 * The axis a home control chooses from, and its options.
 *
 * Re-exported rather than restated: which axis files which kind is a fact about the collections
 * themselves, and the scratchpad lift asks the same question when it offers somewhere to lift into.
 */
export type HomeAxis = CollectionAxis
export const homeOptions = filableCollections

/**
 * The home a create form should start on, given the collection the reader is browsing.
 *
 * Empty means "no collection", which is what the write path reads as `uncategorized` — so the
 * control has one blank option rather than a magic slug a reader would have to recognise.
 *
 * Only offered where that collection is actually one of the choices: browsing an axis this kind is
 * not filed on, or a collection since archived, would otherwise default the form to a home the
 * select cannot show and the reader cannot see.
 */
export const defaultHome = (
  browsed: string,
  options: readonly GroupEntry[],
): string => (options.some((entry) => entry.slug === browsed) ? browsed : '')

/** The collection an artifact sits in when it belongs to no project. Published by every read. */
export const NO_COLLECTION = 'uncategorized'

/**
 * The wire value for a home on a **create**: absent, where none was chosen.
 *
 * Absent and `uncategorized` mean the same thing to a create, and absent is the one that does not
 * ask a caller to know the slug.
 */
export const homeForCreate = (chosen: string): string | undefined => chosen || undefined

/**
 * The wire value for a home on an **edit**, where the two readings come apart.
 *
 * Absent leaves the artifact where it is, so it cannot express "take it out of its collection" —
 * for that the move has to name `uncategorized`, which is a real collection rather than the absence
 * of one. A control whose blank option quietly meant "leave it" would offer a move it never made.
 */
export const homeForMove = (chosen: string): string => chosen || NO_COLLECTION

/**
 * The home an edit form starts on, read from the artifact itself.
 *
 * `uncategorized` becomes the blank option: the control offers "No collection" as a real answer,
 * and showing a slug there would name the absence of a collection as if it were one.
 */
export const homeFromArtifact = (group: string | null | undefined): string =>
  group === NO_COLLECTION ? '' : (group ?? '')
