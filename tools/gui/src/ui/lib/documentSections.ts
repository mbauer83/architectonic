import type { SectionSpec } from '../../domain'

// Mirrors `_SECTION_HEADING_RE` in `_verifier_document.py` (`^##\s+(.+)$`, multiline).
const SECTION_HEADING_RE = /^##\s+(.+)$/gm

export function sectionAtOffset(body: string, offset: number): string | null {
  const text = body.slice(0, Math.max(0, offset))
  SECTION_HEADING_RE.lastIndex = 0
  let lastName: string | null = null
  let match: RegExpExecArray | null
  while ((match = SECTION_HEADING_RE.exec(text)) !== null) {
    lastName = match[1].trim()
  }
  return lastName
}

export function findSectionSpec(
  sections: readonly SectionSpec[] | undefined,
  name: string | null,
): SectionSpec | null {
  if (!name) return null
  return sections?.find((section) => section.name === name) ?? null
}

// ── Reference terms ───────────────────────────────────────────────────────────
//
// Mirrors `parse_reference_term` in `src/application/artifacts/reference_terms.py`, which owns the
// syntax. A term names one of three vocabularies: an entity type or element class bare, a document
// type behind `doc:`, a diagram type behind `diagram:`. The kind matters here and not only in the
// label, because the entity-search ranking below must not rank a document type as an entity type.

export type ReferenceKind = 'entity' | 'document' | 'diagram'

const KIND_PREFIXES: ReadonlyArray<readonly [string, ReferenceKind]> = [
  ['doc:', 'document'],
  ['diagram:', 'diagram'],
]

const ANY_TERM = '@all'

const ANY_LABELS: Readonly<Record<ReferenceKind, string>> = {
  entity: 'Any entity',
  document: 'Any document',
  diagram: 'Any diagram',
}

const KIND_SUFFIXES: Readonly<Record<ReferenceKind, string>> = {
  entity: '',
  document: ' document',
  diagram: ' diagram',
}

export interface ReferenceTerm {
  readonly kind: ReferenceKind
  readonly body: string
}

/** As much of a document type as labelling a `doc:` term needs. */
export interface DocumentTypeLabel {
  readonly doc_type: string
  readonly name: string
}

export function parseReferenceTerm(term: string): ReferenceTerm {
  const written = term.trim()
  for (const [prefix, kind] of KIND_PREFIXES) {
    if (written.startsWith(prefix)) {
      return { kind, body: written.slice(prefix.length).trim() }
    }
  }
  return { kind: 'entity', body: written }
}

export function sectionReferenceTerms(section: SectionSpec | null): string[] {
  if (!section) return []
  return [
    ...(section.required_connections ?? []),
    ...(section.suggested_connections ?? []),
  ]
}

const humanise = (body: string) =>
  body.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/**
 * The term in the words a chip should show it in.
 *
 * `documentTypes` is the catalog a caller already holds, so a `doc:` chip can read
 * "Architecture Decision Record document" rather than the slug the schema spells. Diagram types
 * have no such catalog on this surface and fall back to the humanised slug, which reads as the
 * label anyway ("C4 Container diagram").
 */
export function formatReferenceTerm(
  term: string,
  documentTypes: readonly DocumentTypeLabel[] = [],
): string {
  const { kind, body } = parseReferenceTerm(term)
  if (body === ANY_TERM) return ANY_LABELS[kind]
  const normalized = body.startsWith('@') ? body.slice(1) : body
  const declared =
    kind === 'document' ? documentTypes.find((type) => type.doc_type === body)?.name : undefined
  return `${declared ?? humanise(normalized)}${KIND_SUFFIXES[kind]}`
}

/** Whether a term names one concrete entity type, rather than a class or another vocabulary. */
export function isLiteralEntityTypeTerm(term: string): boolean {
  const { kind, body } = parseReferenceTerm(term)
  return kind === 'entity' && !body.startsWith('@')
}

/**
 * The entity types an entity search should rank first.
 *
 * Filtered by kind as well as by the class sigil: a `doc:` or `diagram:` term names no entity type,
 * and ranking by one would promote whatever entity happened to share the name.
 */
export function rankedEntityTypeSet(terms: readonly string[] | undefined): Set<string> {
  return new Set(
    (terms ?? []).filter(isLiteralEntityTypeTerm).map((term) => parseReferenceTerm(term).body),
  )
}
