/**
 * Pure helpers for `ViewpointsManagementView.vue`: the semantic-edit-vs-descriptive-edit
 * diff that drives the version-bump hint (mirrors `_semantic_snapshot`/`_validate_lifecycle`
 * in `src/domain/viewpoints/viewpoint_validation.py` — scope/query/presentation/representation_types
 * are the semantic fields; everything else is descriptive), and small text-field helpers.
 */

import { definitionToMapping } from '../../domain/viewpointDefinitionSerialization'
import type { ViewpointDefinitionDraft } from '../../domain/viewpointDefinitionDraft'
import { resolveIssuePathNodeId } from '../../domain/viewpointIssuePath'
import type { ScopeSummary, ViewpointExecutionResult, ViewpointValidationIssue } from '../../domain'
import type { Representation } from '../../domain/viewpointPresentation'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import type { ViewpointDefinitionEnvelope } from '../../domain'
import { entityListRoute, graphExploreRoute, viewpointDiagramRoute, viewpointMatrixRoute } from '../router/artifactRoutes'

/** Route to the representation-appropriate execution surface, pre-loaded with a
 * viewpoint's repository-context population — no separate anchor entity required.
 * Shared by the management list and the Home pinned-definitions section so a slug always
 * lands on the same surface regardless of which page linked to it. */
const EXECUTION_ROUTE_BY_REPRESENTATION: Record<Representation, (slug: string) => ExecutionRoute> = {
  // Exploration and table execute a viewpoint *over* a collection: the slug selects which
  // population the surface shows, which is an operand, so it stays in the query. Matrix and
  // diagram address the projection itself, and its identity is the slug — so that goes in the path.
  exploration: (slug) => ({ path: graphExploreRoute(), query: { viewpoint: slug } }),
  table: (slug) => ({ path: entityListRoute(), query: { viewpoint: slug } }),
  matrix: (slug) => ({ path: viewpointMatrixRoute(slug) }),
  diagram: (slug) => ({ path: viewpointDiagramRoute(slug) }),
}

export interface ExecutionRoute {
  readonly path: string
  readonly query?: { readonly viewpoint: string }
}

export const executionRouteFor = (envelope: ViewpointDefinitionEnvelope): ExecutionRoute => {
  const representation = presentationFromMapping(envelope.presentation)?.representation ?? 'exploration'
  return EXECUTION_ROUTE_BY_REPRESENTATION[representation](envelope.slug)
}

/** Execution surfaces title by human name, slug secondary: "Name (slug)" — never the
 * raw slug alone. Falls back to the slug while the catalog is still loading. */
export const executionTitleFor = (
  slug: string,
  definitions: readonly ViewpointDefinitionEnvelope[],
): string => {
  const envelope = definitions.find((d) => d.slug === slug)
  return envelope ? `${envelope.name} (${slug})` : slug
}

const SEMANTIC_KEYS = ['scope', 'query', 'presentation', 'representation_types'] as const

/** True when any semantic field differs from `original` — a real editor never diffs by
 * field name directly since `definitionToMapping` is the one place both this and the
 * server agree on what "the same value" means (default-omission, sort order, ...). */
export const isSemanticEdit = (current: ViewpointDefinitionDraft, original: ViewpointDefinitionDraft): boolean => {
  const currentMapping = definitionToMapping(current)
  const originalMapping = definitionToMapping(original)
  return SEMANTIC_KEYS.some((key) => JSON.stringify(currentMapping[key]) !== JSON.stringify(originalMapping[key]))
}

export const csvToList = (text: string): string[] => text.split(',').map((v) => v.trim()).filter((v) => v.length > 0)
export const listToCsv = (list: readonly string[]): string => list.join(', ')

export const formatScopeSummary = (summary: ScopeSummary): string => {
  if (summary.unrestricted) return 'unrestricted'
  const parts: string[] = []
  if (summary.entity_types) parts.push(`entities: ${summary.entity_types.join(', ')}`)
  if (summary.connection_types) parts.push(`connections: ${summary.connection_types.join(', ')}`)
  if (summary.excluded_domains) parts.push(`excludes domains: ${summary.excluded_domains.join(', ')}`)
  if (summary.excluded_entity_types) parts.push(`excludes entities: ${summary.excluded_entity_types.join(', ')}`)
  if (summary.excluded_connection_types) parts.push(`excludes connections: ${summary.excluded_connection_types.join(', ')}`)
  return parts.join('; ') || 'unrestricted'
}

// ── Live preview + test-run before save ──────────────────────────────────────

/** Debounced live-preview counts (total counts only — a `limit: 0` execution never
 * fetches entity/connection records, so it stays cheap enough to run on every settled
 * keystroke while building criteria). */
export const formatPreviewCounts = (
  result: Pick<ViewpointExecutionResult, 'total_entity_count' | 'total_connection_count'> | null,
): string => {
  if (!result) return ''
  const { total_entity_count: entities, total_connection_count: connections } = result
  return `${entities} entit${entities === 1 ? 'y' : 'ies'} / ${connections} connection${connections === 1 ? '' : 's'}`
}

// ── Save As (fork a definition into a new engagement viewpoint) ──────────────

/** A unique slug for a fork of *slug*: `<slug>-copy`, then `<slug>-copy-2`, … — slugs are
 * unique across the merged catalog (module ∪ enterprise ∪ engagement), so the suggestion
 * must dodge every tier, not just engagement-owned definitions. */
export const suggestForkSlug = (slug: string, existingSlugs: readonly string[]): string => {
  const taken = new Set(existingSlugs)
  const base = `${slug}-copy`
  if (!taken.has(base)) return base
  let counter = 2
  while (taken.has(`${base}-${counter}`)) counter += 1
  return `${base}-${counter}`
}

/** The builder-node id to highlight for a full test-run's save-mode validation issues —
 * same convention `save()`'s real persist-error path already uses, so a definition that
 * fails validation points at the same offending node whether caught by a test-run or by an
 * actual save attempt. */
export const firstErrorNodeId = (
  issues: readonly ViewpointValidationIssue[],
  draft: ViewpointDefinitionDraft,
): string | null => {
  const firstError = issues.find((issue) => issue.severity === 'error')
  return firstError ? resolveIssuePathNodeId(firstError.path, draft) : null
}

/** Indices of style rules a dry-run persist rejected — the fork-safe quarantine set.
 * Only error-severity issues anchored under a specific rule count. */
export const failingStyleRuleIndices = (
  issues: readonly ViewpointValidationIssue[],
): ReadonlySet<number> => {
  const failing = new Set<number>()
  for (const validationIssue of issues) {
    if (validationIssue.severity !== 'error') continue
    const match = /^\/presentation\/styling_rules\/(\d+)(\/|$)/.exec(validationIssue.path)
    if (match) failing.add(Number(match[1]))
  }
  return failing
}

/** Unsaved-work check for the editor's discard guard: a read-only view is never dirty;
 * an edit is dirty when the draft's wire mapping differs from the original's; a
 * create/fork is dirty as soon as it exists (there is no saved original). */
export const isDraftDirty = (
  draft: ViewpointDefinitionDraft | null,
  originalDraft: ViewpointDefinitionDraft | null,
  options: { isCreating: boolean; isReadOnly: boolean },
): boolean => {
  if (!draft || options.isReadOnly) return false
  if (!originalDraft) return options.isCreating
  return JSON.stringify(definitionToMapping(draft)) !== JSON.stringify(definitionToMapping(originalDraft))
}
