/**
 * Deleting an attribute on the entity page and saving removes it.
 *
 * The regression: the form dropped the deleted row from the body, the server read the missing key as
 * "keep it", and the save succeeded without changing anything. This drives the form the way the page
 * does — start editing, remove a row, save — and reads the body the service was handed.
 */
import { Effect } from 'effect'
import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { ModelService } from '../../../application/ModelService'
import type { EntityDetail, EntitySchemaInfo } from '../../../domain'
import { useEntityEditForm } from '../useEntityEditForm'

const schema: EntitySchemaInfo = {
  artifact_type: 'requirement', specialization: '', properties: [], required: [],
  descriptors: {}, conflicts: [], quarantined: false,
}

const entity = {
  artifact_id: 'REQ@1.a.attribute-removal',
  artifact_type: 'requirement',
  name: 'Attribute Removal',
  status: 'draft',
  properties: { Rationale: 'kept', Retries: 3 },
  extra: { 'attribute-types': { Retries: 'integer' } },
} as unknown as EntityDetail

const flush = async () => { for (let i = 0; i < 4; i += 1) await Promise.resolve() }

describe('removing an attribute in the entity edit form', () => {
  it('sends the removed attribute and its type as null', async () => {
    const editEntity = vi.fn<(id: string, body: Record<string, unknown>) => Effect.Effect<unknown>>(
      () => Effect.succeed({ wrote: true, artifact_id: entity.artifact_id }),
    )
    const svc = {
      getEntitySchemata: vi.fn(() => Effect.succeed(schema)),
      getAuthoringGuidance: vi.fn(() => Effect.fail('not needed here')),
    } as unknown as ModelService
    const edit = useEntityEditForm({
      svc,
      entityId: computed(() => entity.artifact_id),
      detail: ref(entity),
      editFn: ref(editEntity as unknown as ModelService['editEntity']),
      onSaved: () => {},
    })

    edit.startEdit()
    await flush()
    edit.removePropertyRow(edit.editProperties.findIndex((row) => row.key === 'Retries'))
    edit.saveEdit()
    await flush()

    expect(editEntity).toHaveBeenCalledOnce()
    const body = editEntity.mock.calls[0]?.[1] ?? {}
    expect(body.properties).toEqual({ Rationale: 'kept', Retries: null })
    expect(body.attribute_types).toEqual({ Retries: null })
  })
})
