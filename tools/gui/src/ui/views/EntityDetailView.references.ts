/**
 * How each kind of "where does this appear" reference reads as a row.
 *
 * Beside the view that asks, not inside the list that draws: the list is handed rows and never learns
 * which kind it is showing, so the vocabulary — what a document's section means, that a diagram
 * carries an ArchiMate type worth stripping its prefix from, that a pad carries neither — stays with
 * the caller that owns it.
 *
 * Each mapping answers the same four questions, which is what made one list component possible: what
 * the section is called, where a row links to, what it is named, and what qualifies it.
 */
import type { EntityDetail } from '../../domain'
import type { EntityReferenceRow } from '../components/entityReferenceRow'

type DocumentReferences = NonNullable<EntityDetail['referenced_in_documents']>
type DiagramReferences = NonNullable<EntityDetail['referenced_in_diagrams']>
type ScratchpadReferences = NonNullable<EntityDetail['referenced_in_scratchpads']>

/** A status worth saying out loud. `active` is the unremarkable case and saying it adds noise. */
const statusMeta = (status: string): string => (status === 'active' ? '' : status)

export const documentReferenceRows = (references: DocumentReferences): EntityReferenceRow[] =>
  references.map((ref) => ({
    // Three fields, because one document can reference an entity from several sections and a section
    // from several links; any one of them alone repeats.
    key: `${ref.document_id}:${ref.section}:${ref.href}`,
    to: `/documents/${encodeURIComponent(ref.document_id)}`,
    name: ref.title,
    meta: ref.section ? `${ref.doc_type} · ${ref.section}` : ref.doc_type,
  }))

export const diagramReferenceRows = (references: DiagramReferences): EntityReferenceRow[] =>
  references.map((ref) => ({
    key: ref.artifact_id,
    to: `/diagrams/${encodeURIComponent(ref.artifact_id)}`,
    name: ref.name,
    // The type says which language the picture is in, and a draft diagram drawing an entity is a
    // weaker statement than an active one — a reader asking where something is used needs both.
    meta: [ref.diagram_type.replace('archimate-', ''), statusMeta(ref.status)]
      .filter(Boolean)
      .join(' · '),
  }))

export const scratchpadReferenceRows = (references: ScratchpadReferences): EntityReferenceRow[] =>
  references.map((ref) => ({
    key: ref.artifact_id,
    to: `/scratchpads/${encodeURIComponent(ref.artifact_id)}`,
    name: ref.name,
    meta: statusMeta(ref.status),
  }))
