/**
 * A details edit that leaves a schema attribute empty states nothing about it.
 *
 * The regression: the form shows a row for every attribute the effective schema declares, and sent the
 * row nobody filled in as `"Telemetry": ""`. Every save wrote an empty row, and on a candidate's canvas
 * (and the diagram editor) any *Edit details* read as a change to the entity's properties. This drives
 * the form as the page and the canvas do — start editing, keep everything, save — and reads the body.
 */
import { Effect } from 'effect'
import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { ModelService } from '../../../application/ModelService'
import type { EntityDetail, EntitySchemaInfo } from '../../../domain'
import { editsOf } from '../../../domain/candidates/candidateCanvas'
import { useEntityEditForm } from '../useEntityEditForm'

const schema: EntitySchemaInfo = {
  artifact_type: 'application-component', specialization: '', properties: ['Telemetry'], required: [],
  descriptors: { Telemetry: { type: 'string', enum: ['None', 'Logs'] } }, conflicts: [], quarantined: false,
}

const entityWith = (properties: Record<string, unknown>) => ({
  artifact_id: 'APP@1.a.renderer',
  artifact_type: 'application-component',
  name: 'Renderer',
  status: 'draft',
  properties,
  extra: {},
}) as unknown as EntityDetail

const flush = async () => { for (let i = 0; i < 4; i += 1) await Promise.resolve() }

const formOver = (entity: EntityDetail, keep?: (body: Record<string, unknown>) => Promise<string | null>) => {
  const editEntity = vi.fn<(id: string, body: Record<string, unknown>) => Effect.Effect<unknown>>(
    () => Effect.succeed({ wrote: true, artifact_id: entity.artifact_id }),
  )
  const svc = {
    getEntitySchemata: vi.fn(() => Effect.succeed(schema)),
    getAuthoringGuidance: vi.fn(() => Effect.fail('not needed here')),
  } as unknown as ModelService
  const edit = useEntityEditForm({
    svc, entityId: computed(() => entity.artifact_id), detail: ref(entity),
    editFn: ref(editEntity as unknown as ModelService['editEntity']), onSaved: () => {}, keep,
  })
  return { edit, editEntity }
}

describe('an empty schema attribute in the entity edit form', () => {
  it('is not sent: a save that changed nothing states no property', async () => {
    const { edit, editEntity } = formOver(entityWith({}))
    edit.startEdit()
    await flush()
    expect(edit.editProperties.map((row) => row.key)).toContain('Telemetry')

    edit.saveEdit()
    await flush()

    expect(editEntity.mock.calls[0]?.[1]?.properties).toEqual({})
  })

  it('records no property edit in a candidate when Edit details is kept unchanged', async () => {
    let kept: Record<string, unknown> | null = null
    const { edit } = formOver(entityWith({}), (body) => { kept = body; return Promise.resolve(null) })
    edit.startEdit()
    await flush()

    edit.saveEdit()
    await flush()

    const command = { op: 'model.element.edit' as const, artifact_id: 'APP@1.a.renderer', ...kept! }
    const edits = editsOf(command)
    expect(edits.filter((one) => one.field === 'properties')).toEqual([])
  })

  it('removes an attribute whose value was emptied', async () => {
    const { edit, editEntity } = formOver(entityWith({ Telemetry: 'Logs' }))
    edit.startEdit()
    await flush()
    edit.editProperties.find((row) => row.key === 'Telemetry')!.value = ''

    edit.saveEdit()
    await flush()

    expect(editEntity.mock.calls[0]?.[1]?.properties).toEqual({ Telemetry: null })
  })

  it('leaves alone an empty row the entity already carries, which states nothing either', async () => {
    const { edit, editEntity } = formOver(entityWith({ Telemetry: '' }))
    edit.startEdit()
    await flush()

    edit.saveEdit()
    await flush()

    expect(editEntity.mock.calls[0]?.[1]?.properties).toEqual({})
  })
})
