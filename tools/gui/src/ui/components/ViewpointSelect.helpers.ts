import type { ViewpointSummary } from '../../domain'

/** Compact label for a viewpoint <option> — name plus version, since a slug can carry
 * multiple versions over its lifetime and the selector must disambiguate them. */
export const viewpointOptionLabel = (viewpoint: ViewpointSummary): string =>
  `${viewpoint.name} (v${viewpoint.version})`

export const findViewpointBySlug = (
  viewpoints: readonly ViewpointSummary[], slug: string | null,
): ViewpointSummary | null =>
  slug === null ? null : viewpoints.find((v) => v.slug === slug) ?? null
