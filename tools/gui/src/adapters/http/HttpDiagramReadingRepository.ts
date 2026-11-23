import { Effect, Schema } from 'effect'
import type { DiagramReadingRepository } from '../../ports/DiagramReadingRepository'
import { lensParams, type ReadingLens } from '../../domain/readingLens'
import { DiagramAttributePanelSchema } from '../../domain/schemas/diagrams'
import { DiagramTypeMemberItemSchema } from '../../domain/schemas/authoring-guidance'
import { DerivedNeighborhoodSchema } from '../../domain/schemas/entities'
import { encodeIdentitySegment } from '../../domain/identitySegments'
import { buildUrl, fetchJson, fetchText } from './httpTransport'

/** The diagram-reading half of the HTTP adapter: the picture, its lens, and what the reader follows. */
export const diagramReadingMethods = (): DiagramReadingRepository => ({
  getDiagramSvg: (diagramId: string, lens?: ReadingLens) =>
    fetchText(buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/svg`, lens && lensParams(lens))),

  getDiagramAttributePanel: (diagramId: string) =>
    fetchJson(buildUrl(`/diagrams/${encodeIdentitySegment(diagramId)}/attribute-panel`), DiagramAttributePanelSchema),

  getDiagramTypeConnectionTypes: (diagramType: string) =>
    fetchJson(
      buildUrl(`/diagram-types/${encodeURIComponent(diagramType)}/connection-types`),
      Schema.Struct({ items: Schema.Array(DiagramTypeMemberItemSchema) }),
    ).pipe(Effect.map((response) => response.items)),

  // No hop count: the server derives within its configured bound, which this client has no business restating.
  getDerivedNeighbors: (entityId: string) =>
    fetchJson(
      buildUrl(`/entities/${encodeIdentitySegment(entityId)}/neighbors`, {
        traversal: 'derived', include_potential: true,
      }),
      DerivedNeighborhoodSchema,
    ).pipe(Effect.map((response) => response.neighbors)),
})
