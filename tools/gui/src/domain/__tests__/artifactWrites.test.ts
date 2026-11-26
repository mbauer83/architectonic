/** Each write of an artifact names the operation the permission answer is read for. */
import { describe, expect, it } from 'vitest'
import { artifactWrites } from '../artifactWrites'

describe('the writes of an artifact', () => {
  it('are the engagement writes for an engagement artifact, whatever the mode', () => {
    for (const adminMode of [false, true]) {
      const writes = artifactWrites(false, adminMode)
      expect(writes.editEntity).toBe('entities_update_entity')
      expect(writes.deleteEntity).toBe('entities_delete_entity')
      expect(writes.deleteDiagram).toBe('diagrams_delete_diagram')
      expect([writes.addConnection, writes.removeConnection, writes.editConnection]).toEqual([
        'connections_create_connection', 'connections_delete_connection', 'connections_update_connection',
      ])
      expect(writes.upstream).toBe(false)
    }
  })

  it('are the admin writes for an enterprise artifact, which the backend refuses outside admin mode', () => {
    for (const adminMode of [false, true]) {
      const writes = artifactWrites(true, adminMode)
      expect([writes.deleteEntity, writes.deleteDiagram, writes.addConnection, writes.removeConnection]).toEqual([
        'admin_delete_entity', 'admin_delete_diagram', 'admin_create_connection', 'admin_delete_connection',
      ])
      expect(writes.editConnection).toBeNull()
    }
  })

  it('edit an enterprise entity upstream in admin mode, and record a change otherwise', () => {
    expect(artifactWrites(true, true)).toMatchObject({ editEntity: 'admin_update_entity', upstream: true })
    expect(artifactWrites(true, false)).toMatchObject({ editEntity: 'entities_update_entity', upstream: false })
  })

  it('offer an enterprise relation\'s associations only in admin mode', () => {
    expect(artifactWrites(true, true).editAssociations).toBe('connections_update_connection_associations')
    expect(artifactWrites(true, false).editAssociations).toBeNull()
  })
})
