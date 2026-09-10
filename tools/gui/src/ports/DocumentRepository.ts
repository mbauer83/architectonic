import type { Effect } from 'effect'
import type { DocumentDetail, DocumentList, DocumentType, NotFoundError, WriteResult } from '../domain'
import type { RepoError } from './repositoryErrors'

/**
 * The document surface, split out the way the admin, scratchpad and diagram-reading surfaces are.
 *
 * `ModelRepository` extends it, so every existing caller keeps working unchanged — what moves is
 * where the six methods are declared, not who can reach them. Split because the composite had
 * reached the source-length policy's ceiling exactly, and a port that cannot take another method
 * without breaking a gate is one asking to be divided along a seam it already has.
 */
export interface DocumentRepository {
  readonly listDocumentTypes: () => Effect.Effect<DocumentType[], RepoError>
  readonly listDocuments: (params?: {
    doc_type?: string; status?: string; limit?: number; offset?: number; group?: string; scope?: string;
  }) => Effect.Effect<DocumentList, RepoError>
  readonly getDocument: (id: string) => Effect.Effect<DocumentDetail, RepoError | NotFoundError>
  readonly createDocument: (body: {
    doc_type: string; title: string; body?: string;
    /** The model-project collection this artifact is filed in — its home. */
    group?: string;
    keywords?: string[]; extra_frontmatter?: Record<string, unknown>;
    version?: string; status?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly editDocument: (id: string, body: {
    title?: string; body?: string; keywords?: string[];
    /** Move it to this collection. Omitted leaves it where it is. */
    group?: string;
    extra_frontmatter?: Record<string, unknown>;
    status?: string; version?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly deleteDocument: (id: string) => Effect.Effect<void, RepoError>
}
