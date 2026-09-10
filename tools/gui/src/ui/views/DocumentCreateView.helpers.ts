import type { DocumentType } from '../../domain'

/**
 * Pure derivations the document create form makes from its selected type.
 *
 * Beside the view rather than inside it, the way the entity create form already keeps its own
 * (`EntityCreateView.helpers.ts`). These are functions of their inputs and nothing else, which is
 * what makes them testable without mounting a form — and what makes the view shorter by exactly
 * the part that never needed to be in it.
 */

/** A body pre-filled with the type's required sections, so an author starts inside the shape. */
export const placeholderBody = (requiredSections: readonly string[]): string =>
  requiredSections.map((section) => `## ${section}\n\n`).join('\n')

/** A frontmatter field's name as a label: `decision_drivers` reads "Decision Drivers". */
export const formatFieldLabel = (name: string): string =>
  name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/**
 * The sections worth pointing an author at, being the ones that name connections.
 *
 * A section with neither required nor suggested connections has no hint to give, and listing it
 * would fill the panel with rows that say nothing.
 */
export const sectionsWithLinkHints = (
  type: DocumentType | null,
): readonly NonNullable<DocumentType['sections']>[number][] =>
  (type?.sections ?? []).filter(
    (section) =>
      (section.required_connections?.length ?? 0) > 0 ||
      (section.suggested_connections?.length ?? 0) > 0,
  )

/**
 * The extra frontmatter a create should carry: the fields an author actually filled in.
 *
 * An empty string and an empty list are both "not filled in" — sending either would write a key
 * whose value says nothing, and the document's frontmatter is read by people.
 */
export const filledExtraFrontmatter = (
  fields: readonly { name: string }[],
  values: Readonly<Record<string, unknown>>,
): Record<string, unknown> | undefined => {
  const result: Record<string, unknown> = {}
  for (const field of fields) {
    const value = values[field.name]
    if (Array.isArray(value) && value.length > 0) result[field.name] = value
    else if (typeof value === 'string' && value.trim()) result[field.name] = value.trim()
  }
  return Object.keys(result).length > 0 ? result : undefined
}
