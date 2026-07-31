import type { Effect } from 'effect'
import type { WriteResult } from '../domain'
import type { RepoError } from './repositoryErrors'

/**
 * Writes against the enterprise tier, active only in `--admin-mode`.
 *
 * A separate port because it is a separate authority: these operations target the enterprise
 * repository with the `enterprise_admin_authoring` intent, and every one of them is refused with a
 * 403 unless the backend was started in admin mode. Keeping them beside the engagement writes made
 * one interface where a reader could not tell which tier a method touched.
 */
export interface EnterpriseAdminRepository {
  readonly adminCreateEntity: (body: {
    artifact_type: string; name: string; summary?: string;
    properties?: Record<string, string>; notes?: string;
    keywords?: string[]; version?: string; status?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly adminEditEntity: (id: string, body: {
    name?: string; summary?: string;
    properties?: Record<string, string>; attribute_types?: Record<string, string>;
    notes?: string; keywords?: string[]; specialization?: string; version?: string; status?: string;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly previewAdminDeleteEntity: (id: string) => Effect.Effect<WriteResult, RepoError>
  readonly adminDeleteEntity: (id: string) => Effect.Effect<void, RepoError>
  readonly adminAddConnection: (body: {
    source_entity: string; connection_type: string; target_entity: string;
    description?: string; src_multiplicity?: string; tgt_multiplicity?: string;
    specialization?: string;
    dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly previewAdminRemoveConnection: (connectionId: string) => Effect.Effect<WriteResult, RepoError>
  readonly adminRemoveConnection: (connectionId: string) => Effect.Effect<void, RepoError>
  readonly previewAdminDeleteDiagram: (id: string) => Effect.Effect<WriteResult, RepoError>
  readonly adminDeleteDiagram: (id: string) => Effect.Effect<void, RepoError>
}
