import { Effect, Exit } from 'effect'
import type { ArtifactSearchHit } from '../../domain'
import type { ModelService } from '../../application/ModelService'

export type PromotionArtifactKind = 'entity' | 'document' | 'diagram'
export type ConflictStrategy = 'accept_engagement' | 'accept_enterprise' | 'merge'
export type Step = 'pick' | 'review' | 'execute' | 'done'

export type PromotionArtifact = {
  artifact_id: string
  name: string
  record_type: PromotionArtifactKind
  status: string
}

export const artifactKindLabel = (kind: PromotionArtifactKind) => {
  if (kind === 'entity') return 'Entity'
  if (kind === 'document') return 'Document'
  return 'Diagram'
}

export const formatArtifactFallbackName = (artifactId: string) => {
  const parts = artifactId.split('.')
  return parts.length > 2 ? parts.slice(2).join(' ').replace(/-/g, ' ') : artifactId
}

const isPromotionArtifact = (
  hit: ArtifactSearchHit,
): hit is ArtifactSearchHit & { record_type: PromotionArtifactKind } =>
  hit.record_type === 'entity' || hit.record_type === 'document' || hit.record_type === 'diagram'

export const searchPromotionArtifacts = (
  svc: ModelService,
  query: string,
  excludedIds: Set<string>,
)=>
  query.trim().length < 2
    ? Effect.succeed<PromotionArtifact[]>([])
    :
    svc.artifactSearch(query.trim(), { limit: 20, include_documents: true, include_diagrams: true }).pipe(
      Effect.map((result) =>
        result.hits
          .filter(isPromotionArtifact)
          .filter((hit) => !excludedIds.has(hit.artifact_id))
          .map((hit) => ({
            artifact_id: hit.artifact_id,
            name: hit.name,
            record_type: hit.record_type,
            status: hit.status,
          })),
      ),
    )

export const loadPromotionEntity = async (svc: ModelService, artifactId: string) => {
  const exit = await Effect.runPromiseExit(svc.getEntity(artifactId))
  return Exit.match(exit, {
    onSuccess: (entity) => ({
      artifact_id: entity.artifact_id,
      name: entity.name,
      artifact_type: entity.artifact_type,
      domain: entity.domain,
      subdomain: entity.subdomain,
      status: entity.status,
      display_alias: '',
      element_type: entity.artifact_type,
      element_label: entity.name,
      diagram_internal: false,
    }),
    onFailure: () => null,
  })
}

export const loadPromotionDocument = async (svc: ModelService, artifactId: string, fallbackName: string) => {
  const exit = await Effect.runPromiseExit(svc.getDocument(artifactId))
  return Exit.match(exit, {
    onSuccess: (document) => ({
      artifact_id: document.artifact_id,
      name: document.title,
      record_type: 'document' as const,
      status: document.status,
    }),
    onFailure: () => ({ artifact_id: artifactId, name: fallbackName, record_type: 'document' as const, status: '' }),
  })
}

export const loadPromotionDiagram = async (svc: ModelService, artifactId: string, fallbackName: string) => {
  const exit = await Effect.runPromiseExit(svc.getDiagram(artifactId))
  return Exit.match(exit, {
    onSuccess: (diagram) => ({
      artifact_id: diagram.artifact_id,
      name: diagram.name,
      record_type: 'diagram' as const,
      status: diagram.status,
    }),
    onFailure: () => ({ artifact_id: artifactId, name: fallbackName, record_type: 'diagram' as const, status: '' }),
  })
}

/** The set with *id* toggled — promotion state keeps several expand/include id-sets. */
export const toggledSet = (current: Set<string>, id: string): Set<string> => {
  const next = new Set(current)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}
