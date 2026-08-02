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
  /**
   * A diagram in the enterprise repository, over enterprise entities.
   *
   * Added because the interface declared the two halves of a diagram's life on this tier — a preview
   * and a delete — and no way to bring one into existence. `POST /admin/api/diagrams` has always been
   * served, so the gap was on this side of the boundary: a caller holding this port could delete an
   * enterprise diagram and could not make one, which left the delete reachable only for a diagram some
   * other surface had put there.
   *
   * `entity_ids` and `connection_ids` are the *selection*; the server renders the body from it and
   * records what it drew. Not optional: a diagram whose frontmatter does not name what its body draws
   * is one the verifier refuses, which is what `admin_create_diagram` did for its whole life until
   * something requested it.
   */
  readonly adminCreateDiagram: (body: {
    diagram_type: string; name: string;
    entity_ids: string[]; connection_ids: string[];
    keywords?: string[]; version?: string; status?: string; dry_run?: boolean;
  }) => Effect.Effect<WriteResult, RepoError>
  readonly previewAdminDeleteDiagram: (id: string) => Effect.Effect<WriteResult, RepoError>
  readonly adminDeleteDiagram: (id: string) => Effect.Effect<void, RepoError>
}
