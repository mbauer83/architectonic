import type { Effect } from 'effect'
import type { IconList, IconStyle, ShownIcons } from '../domain/schemas/icons'
import type { WriteResult } from '../domain/schemas/write-results'
import type { RepoError } from './repositoryErrors'

/** An instance as an editor lists it: an occurrence names the entity it draws. */
export interface EditedInstance {
  readonly instance_id: string
  readonly entity_id?: string
}

/** What an icon says about itself; a field left out keeps its value. The picture is not editable. */
export interface IconEdit {
  readonly name?: string
  readonly attribution?: string
  readonly applies_to?: readonly string[]
  readonly default_style?: IconStyle
  readonly tags?: readonly string[]
  readonly status?: 'active' | 'retired'
  readonly dry_run: boolean
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
    /** Whose projection says what a model-backed view draws each entity as. */
    diagram_type?: string
    diagram_entities: Record<string, unknown>
    instances: readonly EditedInstance[]
  }) => Effect.Effect<ShownIcons, RepoError>
  readonly createIcon: (upload: IconUpload) => Effect.Effect<WriteResult, RepoError>
  readonly editIcon: (iconId: string, edit: IconEdit) => Effect.Effect<WriteResult, RepoError>
  /** Re-point every diagram showing the icon at another the library holds, then delete it. */
  readonly replaceIcon: (
    iconId: string, body: { replacement_id: string; dry_run: boolean },
  ) => Effect.Effect<WriteResult, RepoError>
  /** Move an icon a diagram holds for itself into the library; the diagram then names it there. */
  readonly shareIcon: (
    diagramId: string, iconKey: string, body: { attribution: string; tags?: readonly string[]; dry_run: boolean },
  ) => Effect.Effect<WriteResult, RepoError>
  /** Refused while anything shows it; the refusal names what does. */
  readonly deleteIcon: (iconId: string) => Effect.Effect<void, RepoError>
}
