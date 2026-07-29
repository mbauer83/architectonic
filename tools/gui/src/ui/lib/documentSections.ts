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

export function sectionEntityTypeTerms(section: SectionSpec | null): string[] {
  if (!section) return []
  return [
    ...(section.required_entity_type_connections ?? []),
    ...(section.suggested_entity_type_connections ?? []),
  ]
}

export function formatEntityTypeTerm(term: string): string {
  if (term === '@all') return 'Any entity'
  const normalized = term.startsWith('@') ? term.slice(1) : term
  return normalized.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function isLiteralEntityTypeTerm(term: string): boolean {
  return !term.startsWith('@')
}

export function rankedEntityTypeSet(terms: readonly string[] | undefined): Set<string> {
  return new Set((terms ?? []).filter(isLiteralEntityTypeTerm))
}
