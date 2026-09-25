import type { IconStyle } from '../../domain/schemas/icons'
import { statementsIn, withStatements } from './diagramStatements'

/**
 * What a diagram states about its elements' icons, in its own `diagram_entities`.
 *
 * `display_icons` maps an instance id — the entity's id for its base drawing, an occurrence's id for a
 * further one — to an icon; `type_icons` maps a type or specialization name to one. An icon is named
 * `ICO@…` from the library or `local:<key>` from `icons`, the ones the diagram holds for itself, and a
 * statement may fix its style. Which icon an element then shows is the server's to say
 * (`previewShownIcons`), so nothing here works out precedence.
 */
export const DISPLAY_ICONS_KEY = 'display_icons'
export const TYPE_ICONS_KEY = 'type_icons'
export const LOCAL_ICONS_KEY = 'icons'

/** Where a diagram states an element's icon: for the element itself, or for every element of its type. */
export type IconScope = 'instance' | 'type'

export interface IconStatement {
  readonly icon: string
  /** Absent takes the icon's own default style. */
  readonly style?: IconStyle
}

const LOCAL_PREFIX = 'local:'

const stored = (statement: IconStatement): string | Record<string, string> =>
  statement.style ? { icon: statement.icon, style: statement.style } : statement.icon

const readStatement = (value: unknown): IconStatement | undefined => {
  if (typeof value === 'string') return { icon: value }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const { icon, style } = value as { icon?: unknown; style?: unknown }
  if (typeof icon !== 'string') return undefined
  return style === 'badge' || style === 'figure' ? { icon, style } : { icon }
}

const withStatement = (key: string) => (
  diagramEntities: Record<string, unknown>, subject: string, statement: IconStatement | null,
): Record<string, unknown> => {
  const statements = statementsIn(diagramEntities, key)
  if (statement) statements[subject] = stored(statement)
  else delete statements[subject]
  return withStatements(diagramEntities, key, statements)
}

const statementOf = (key: string) => (
  diagramEntities: Record<string, unknown>, subject: string,
): IconStatement | undefined => readStatement(statementsIn(diagramEntities, key)[subject])

/** Give one instance its own icon, or withdraw that with `null` so its type's decides again. */
export const withInstanceIcon = withStatement(DISPLAY_ICONS_KEY)
/** Give every element of a type or specialization on this diagram an icon, or withdraw it with `null`. */
export const withTypeIcon = withStatement(TYPE_ICONS_KEY)
export const instanceIconOf = statementOf(DISPLAY_ICONS_KEY)
export const typeIconOf = statementOf(TYPE_ICONS_KEY)

/** Every type or specialization name the diagram gives an icon to. */
export const typesWithIcons = (diagramEntities: Record<string, unknown>): readonly string[] =>
  Object.keys(statementsIn(diagramEntities, TYPE_ICONS_KEY))

export interface IconUploadForDiagram {
  readonly name: string
  readonly content_base64: string
  readonly source_format: 'svg' | 'png' | 'jpeg' | 'webp'
  /** Type and specialization names it may be shown on; empty means any element. */
  readonly applies_to?: readonly string[]
}

/** The key an upload is held under: a slug of its name, made unique among the diagram's own icons. */
export const localIconKeyFor = (diagramEntities: Record<string, unknown>, name: string): string => {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'icon'
  const taken = new Set(Object.keys(statementsIn(diagramEntities, LOCAL_ICONS_KEY)))
  let key = base
  for (let n = 2; taken.has(key); n += 1) key = `${base}-${n}`
  return key
}

/**
 * Hold an upload in the diagram's own icons, where the save stores it normalised; returns the data and
 * the reference that names it. An upload nothing references is dropped by that save, so abandoning an
 * assignment leaves nothing behind.
 */
export const withLocalIcon = (
  diagramEntities: Record<string, unknown>, upload: IconUploadForDiagram,
): { readonly diagramEntities: Record<string, unknown>; readonly icon: string } => {
  const key = localIconKeyFor(diagramEntities, upload.name)
  const icons = { ...statementsIn(diagramEntities, LOCAL_ICONS_KEY), [key]: { ...upload } }
  return { diagramEntities: withStatements(diagramEntities, LOCAL_ICONS_KEY, icons), icon: `${LOCAL_PREFIX}${key}` }
}

export const isLocalIcon = (icon: string): boolean => icon.startsWith(LOCAL_PREFIX)
