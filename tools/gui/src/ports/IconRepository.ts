import type { Effect } from 'effect'
import type { IconList, IconStyle, ShownIcons } from '../domain/schemas/icons'
import type { WriteResult } from '../domain/schemas/write-results'
import type { RepoError } from './repositoryErrors'

/** An instance as an editor lists it: an occurrence names the entity it draws. */
export interface EditedInstance {
  readonly instance_id: string
  readonly entity_id?: string
}

export interface IconUpload {
  readonly name: string
  readonly attribution: string
  readonly content_base64: string
  readonly source_format: 'svg' | 'png' | 'jpeg' | 'webp'
  readonly applies_to?: readonly string[]
  readonly default_style?: IconStyle
  readonly tags?: readonly string[]
  readonly dry_run: boolean
}

/**
 * The icon half of the outbound port: the library a picker offers, and which icon each instance of a
 * diagram shows. The editor asks the second rather than working it out, so the precedence it shows
 * is the one the renderer draws.
 */
export interface IconRepository {
  readonly listIcons: (params?: {
    /** An entity id, or a type or specialization name. */
    applicable_to?: string
    tag?: string
    q?: string
    include_retired?: boolean
  }) => Effect.Effect<IconList, RepoError>
  readonly iconImageUrl: (iconId: string) => string
  readonly previewShownIcons: (body: {
    diagram_entities: Record<string, unknown>
    instances: readonly EditedInstance[]
  }) => Effect.Effect<ShownIcons, RepoError>
  readonly createIcon: (upload: IconUpload) => Effect.Effect<WriteResult, RepoError>
}
