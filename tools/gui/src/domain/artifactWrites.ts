/**
 * Which named operation each write of an artifact is, by where the artifact lives and the backend's mode.
 *
 * Whether a write may be done now is the permission answer's to say (`useCan`), never this module's. An
 * enterprise artifact is written in place by the admin twin of each write, which the backend refuses
 * `admin_mode_required` outside admin mode; this only names the write a control performs, so the answer
 * for it can be read. The one write whose operation depends on the mode is editing an enterprise entity:
 * in admin mode it lands upstream, otherwise it is recorded as a change in the engagement repository.
 *
 * `null` is a write the artifact's tier does not have here, and its control is not offered at all: an
 * enterprise relation has no admin edit, and outside admin mode its associations are not edited here.
 */

export interface ArtifactWrites {
  readonly editEntity: string
  readonly deleteEntity: string
  readonly deleteDiagram: string
  readonly addConnection: string
  readonly removeConnection: string
  readonly editConnection: string | null
  readonly editAssociations: string | null
  /** Whether an edit lands in the enterprise repository directly (admin mode, an enterprise artifact). */
  readonly upstream: boolean
}

const ENGAGEMENT: ArtifactWrites = {
  editEntity: 'entities_update_entity',
  deleteEntity: 'entities_delete_entity',
  deleteDiagram: 'diagrams_delete_diagram',
  addConnection: 'connections_create_connection',
  removeConnection: 'connections_delete_connection',
  editConnection: 'connections_update_connection',
  editAssociations: 'connections_update_connection_associations',
  upstream: false,
}

const ENTERPRISE_IN_PLACE: Omit<ArtifactWrites, 'editEntity' | 'editAssociations' | 'upstream'> = {
  deleteEntity: 'admin_delete_entity',
  deleteDiagram: 'admin_delete_diagram',
  addConnection: 'admin_create_connection',
  removeConnection: 'admin_delete_connection',
  editConnection: null,
}

export const artifactWrites = (enterprise: boolean, adminMode: boolean): ArtifactWrites => {
  if (!enterprise) return ENGAGEMENT
  return adminMode
    ? {
        ...ENTERPRISE_IN_PLACE, editEntity: 'admin_update_entity',
        editAssociations: ENGAGEMENT.editAssociations, upstream: true,
      }
    : { ...ENTERPRISE_IN_PLACE, editEntity: ENGAGEMENT.editEntity, editAssociations: null, upstream: false }
}
