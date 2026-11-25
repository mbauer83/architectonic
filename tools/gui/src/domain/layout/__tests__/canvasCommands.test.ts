/**
 * What a canvas session keeps of its model commands: a rename or a relation edit replaces the one before
 * it, an element's details merge over the ones before them key by key, and the entity form opens a
 * second edit on what the first one kept.
 */
import { describe, expect, it } from 'vitest'
import type { EntityDetail } from '../..'
import type { CanvasCommand } from '../../../ports/diagramWriteBodies'
import { composeCanvas, withCommand, withPendingDetails, withoutDraft } from '../canvasComposition'

const ID = 'SRV@1712870400.Uv9Wx9.repository-promotion-service'
const kept = (...commands: CanvasCommand[]) => commands.reduce(withCommand, [] as CanvasCommand[])

describe('the commands a session keeps', () => {
  it('replaces an earlier rename of the same element, and keeps both of two elements', () => {
    expect(kept(
      { op: 'model.element.rename', artifact_id: ID, name: 'One' },
      { op: 'model.element.rename', artifact_id: 'APP@1.a.b', name: 'Other' },
      { op: 'model.element.rename', artifact_id: ID, name: 'Two' },
    )).toEqual([
      { op: 'model.element.rename', artifact_id: 'APP@1.a.b', name: 'Other' },
      { op: 'model.element.rename', artifact_id: ID, name: 'Two' },
    ])
  })

  it('merges an element\'s details, key by key, so a later edit does not drop an earlier one', () => {
    expect(kept(
      { op: 'model.element.edit', artifact_id: ID, summary: 'First', properties: { owner: 'Ops' } },
      { op: 'model.element.edit', artifact_id: ID, status: 'active', properties: { tier: '1' } },
    )).toEqual([{
      op: 'model.element.edit', artifact_id: ID, summary: 'First', status: 'active',
      properties: { owner: 'Ops', tier: '1' },
    }])
  })
})

describe('the details a second edit opens on', () => {
  const detail = {
    artifact_id: ID, name: 'Service', summary: 'Old', status: 'draft', keywords: [], specializations: [],
    properties: { owner: 'Dev', gone: 'x' },
  } as unknown as EntityDetail

  it('are the model\'s, with what the session kept laid over them', () => {
    const now = withPendingDetails(detail, [
      { op: 'model.element.rename', artifact_id: ID, name: 'Renamed' },
      { op: 'model.element.edit', artifact_id: ID, summary: 'New', properties: { owner: 'Ops', gone: null } },
    ])
    expect([now.name, now.summary, now.status, now.properties]).toEqual(['Renamed', 'New', 'draft', { owner: 'Ops' }])
  })

  it('are the model\'s alone when the session kept nothing for the element', () => {
    expect(withPendingDetails(detail, [{ op: 'model.element.rename', artifact_id: 'APP@1.a.b', name: 'X' }]))
      .toBe(detail)
  })
})

describe('the moves into and out of the diagram\'s own boxes', () => {
  const drawn = {
    diagram_type: 'archimate-layered', name: 'D', entity_ids: [ID], connection_ids: [],
    authored_groupings: [{ id: 'g-Desk1', label: 'Desk', 'entity-ids': [] }],
  }

  it('are stated to the preview and the write alike, for the server to compile', () => {
    const regroupings = [{ intent: 'nest' as const, keys: [ID], grouping: 'g-Desk1' }]
    const { preview, write } = composeCanvas(drawn, { regroupings }, new Set())
    expect(write.grouping_intents).toEqual(regroupings)
    expect(preview.grouping_intents).toEqual(regroupings)
    expect(write.authored_groupings).toEqual(drawn.authored_groupings)
  })

  it('are not stated at all when the session kept none', () => {
    expect('grouping_intents' in composeCanvas(drawn, {}, new Set()).write).toBe(false)
  })
})

describe('a further drawing of an element', () => {
  const stored = { id: 'occ-svc-2', backing_entity_id: ID }
  const drawn = {
    diagram_type: 'archimate-layered', name: 'D', entity_ids: [ID], connection_ids: [],
    diagram_entities: { occurrence: [stored] },
  }

  it('added in the session joins the occurrence statement the diagram already makes', () => {
    const added = { id: 'occ-svc-3', backing_entity_id: ID }
    const { write, preview } = composeCanvas(drawn, { occurrences: [added] }, new Set())
    expect(write.diagram_entities?.occurrence).toEqual([stored, added])
    expect(preview.diagram_entities?.occurrence).toEqual([stored, added])
  })

  it('removed from the diagram, or of an element deleted, leaves the statement', () => {
    expect(composeCanvas(drawn, {}, new Set(['occ-svc-2'])).write.diagram_entities?.occurrence).toEqual([])
    const deleted = composeCanvas(drawn, { commands: [{ op: 'model.element.delete', artifact_id: ID }] }, new Set())
    expect(deleted.write.diagram_entities?.occurrence).toEqual([])
  })
})

describe('a draft discarded', () => {
  const DRAFT = 'BOB@1795000000.Abc123.audit-note'
  const relation = (source: string, target: string): CanvasCommand => ({
    op: 'model.relation.create', artifact_id: `${source}---${target}@@archimate-association`,
    description: '', src_multiplicity: '', tgt_multiplicity: '',
  })

  it('takes its creation and everything proposed about it, and leaves the rest of the session', () => {
    const rest: CanvasCommand[] = [{ op: 'model.element.rename', artifact_id: ID, name: 'Kept' }, relation(ID, 'APP@1.a.b')]
    const session = {
      commands: [
        { op: 'model.element.create', artifact_type: 'business-object', artifact_id: DRAFT, name: 'Note', group: 'g' },
        { op: 'model.element.rename', artifact_id: DRAFT, name: 'Audit note' },
        relation(ID, DRAFT), relation(DRAFT, 'APP@1.a.b'), ...rest,
      ] satisfies CanvasCommand[],
      regroupings: [{ intent: 'nest' as const, keys: [DRAFT, 'APP@1.a.b'], grouping: 'g-1' },
        { intent: 'unnest' as const, keys: [DRAFT] }],
    }
    const left = withoutDraft(session, DRAFT)
    expect(left.commands).toEqual(rest)
    expect(left.regroupings).toEqual([{ intent: 'nest', keys: ['APP@1.a.b'], grouping: 'g-1' }])
  })
})
