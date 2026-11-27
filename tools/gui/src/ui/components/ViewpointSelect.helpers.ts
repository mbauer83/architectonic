import type { ViewpointSummary } from '../../domain'

/** Compact label for a viewpoint <option> — name plus version, since a slug can carry
 * multiple versions over its lifetime and the selector must disambiguate them. */
export const viewpointOptionLabel = (viewpoint: ViewpointSummary): string =>
  `${viewpoint.name} (v${viewpoint.version})`

/** Whether *viewpoint* is intended for *diagramType*: one declaring no types suits any, and so does any
 * viewpoint where no diagram type is in question. */
export const suitsDiagramType = (viewpoint: ViewpointSummary, diagramType: string | undefined): boolean =>
  diagramType === undefined || viewpoint.intended_for.length === 0 || viewpoint.intended_for.includes(diagramType)

/** The picker's options: suited viewpoints first, then the rest, each group in the order given. */
export const viewpointOptions = (
  viewpoints: readonly ViewpointSummary[], diagramType: string | undefined,
): { viewpoint: ViewpointSummary; suited: boolean }[] => {
  const options = viewpoints.map((viewpoint) => ({ viewpoint, suited: suitsDiagramType(viewpoint, diagramType) }))
  return [...options.filter((o) => o.suited), ...options.filter((o) => !o.suited)]
}

/** What marks a viewpoint the picker offers for a diagram type it was not written for. */
export const NOT_INTENDED_NOTE = 'not intended for this diagram type'

export const findViewpointBySlug = (
  viewpoints: readonly ViewpointSummary[], slug: string | null,
): ViewpointSummary | null =>
  slug === null ? null : viewpoints.find((v) => v.slug === slug) ?? null
