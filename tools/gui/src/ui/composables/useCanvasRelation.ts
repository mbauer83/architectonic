/**
 * The relation a canvas popover drafts (sketch 03·8): between two elements, either one the model already
 * holds and this diagram does not draw — kept, it is drawn, diagram content only ("In the model: draw
 * it") — or a new one of a type the ontology permits between them and the model does not hold yet —
 * kept, it is a model change proposed to the session ("Not in the model: create it"). Or a drawn one
 * read back for editing: its stated label, and any edit already pending in the session over the model's.
 */
import { ref, type ComputedRef, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext } from '../../domain'
import { connectionId, stableConnectionId, stableEntityId } from '../../domain/artifactId'
import { isRecord } from '../../domain/records'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import type { DiagramEditing } from './useDiagramEditing'

type Member = { readonly alias: string; readonly id: string; readonly type: string }

export function useCanvasRelation(
  svc: ModelService, editing: DiagramEditing, context: () => DiagramContext,
  members: ComputedRef<readonly Member[]>, ends: { source: Ref<string>; target: Ref<string> },
  opened: () => void, failed: (message: string) => void,
  apply: (command: CanvasCommand, overlay: Record<string, unknown>) => void,
  draw: (id: string, overlay: Record<string, unknown>) => void,
) {
  const options = ref<readonly string[]>([])
  /** The relations the model holds from the source to the target that this diagram does not draw. */
  const inModel = ref<readonly { readonly id: string; readonly type: string }[]>([])
  /** The one of those chosen to be drawn; empty while a type to create is chosen instead. */
  const drawing = ref('')
  const kind = ref('')
  const label = ref('')
  const srcCount = ref('')
  const tgtCount = ref('')
  const description = ref('')
  const currentLine = ref('')
  const member = (alias: string) => members.value.find((e) => e.alias === alias)

  /** The relations the session already draws or creates, by id: what is not offered again. */
  const drawnIds = (): ReadonlySet<string> => {
    const now = editing.session.state.value
    const created = (now?.commands ?? []).flatMap((c) => (c.op === 'model.relation.create' ? [c.artifact_id] : []))
    return new Set([...context().connections.map((one) => one.artifact_id), ...now?.drawnRelations ?? [], ...created]
      .map(stableConnectionId))
  }

  /**
   * A relation from the source to *alias*: offered first those the model holds and this diagram does not
   * draw, then the types the ontology permits between them that the model does not hold.
   */
  const pair = async (alias: string) => {
    const from = member(ends.source.value)
    const to = member(alias)
    if (!from || !to) return
    ends.target.value = alias
    options.value = []
    inModel.value = []
    kind.value = drawing.value = label.value = description.value = srcCount.value = tgtCount.value = ''
    currentLine.value = ''
    opened()
    try {
      const [permitted, held] = await Promise.all([
        Effect.runPromise(svc.getOntologyPair(from.type, to.type)),
        Effect.runPromise(svc.getConnectionsAmong([from.id, to.id])),
      ])
      if (ends.target.value !== alias || ends.source.value !== from.alias) return
      const same = (one: string, other: string) => stableEntityId(one) === stableEntityId(other)
      const drawn = drawnIds()
      inModel.value = held.filter((one) => same(one.source, from.id) && same(one.target, to.id)
        && !drawn.has(stableConnectionId(one.artifact_id))).map((one) => ({ id: one.artifact_id, type: one.conn_type }))
      const types = [...new Set([...permitted.connection_types, ...permitted.symmetric])]
      options.value = types.filter((type) => !held.some((one) => same(one.source, from.id) && same(one.target, to.id)
        && one.conn_type === type))
      drawing.value = inModel.value[0]?.id ?? ''
      kind.value = drawing.value ? '' : options.value[0] ?? ''
    } catch (e) {
      failed(String(e))
    }
  }

  /** The drawn relation at *index*, read back with its stated label and any pending edit over the model's. */
  const editLine = (index: number) => {
    const row = editing.session.geometry.value?.relations.find((r) => r.index === index)
    const record = row && context().connections.find((c) => c.edge_key === row.key)
    if (!row || !record) return
    ends.source.value = row.source
    ends.target.value = row.target
    currentLine.value = record.artifact_id
    options.value = [record.conn_type]
    kind.value = record.conn_type
    drawing.value = ''
    inModel.value = []
    const pending = editing.session.state.value
    const prior = context().diagram.extra?.connections
    const stored = Array.isArray(prior) ? (prior as unknown[]).filter(isRecord) : []
    const overlays = [...stored, ...(pending?.overlays ?? [])]
    const overlay = overlays.reverse()
      .find(r => stableConnectionId(String(r.artifact_id ?? r.connection_id)) === row.key)
    const stated = overlay?.label ?? record.edge_label_override
    label.value = typeof stated === 'string' ? stated : ''
    description.value = record.content_text
    srcCount.value = record.src_multiplicity ?? ''
    tgtCount.value = record.tgt_multiplicity ?? ''
    const edit = pending?.commands?.find(c => c.artifact_id === record.artifact_id && c.op === 'model.relation.edit')
    if (edit && 'src_multiplicity' in edit) {
      description.value = edit.description
      srcCount.value = edit.src_multiplicity
      tgtCount.value = edit.tgt_multiplicity
    }
    opened()
  }

  const keep = () => {
    const from = member(ends.source.value)
    const to = member(ends.target.value)
    if (drawing.value) {
      draw(drawing.value, { artifact_id: drawing.value, label: label.value, include_multiplicity: true })
      return
    }
    if (!from || !to || !kind.value) return
    const id = currentLine.value || connectionId(from.id, kind.value, to.id)
    apply(
      {
        op: currentLine.value ? 'model.relation.edit' : 'model.relation.create',
        artifact_id: id,
        description: description.value,
        src_multiplicity: srcCount.value,
        tgt_multiplicity: tgtCount.value,
      },
      { artifact_id: id, label: label.value, include_multiplicity: true, include_description: true },
    )
  }

  return {
    options, inModel, drawing, kind, label, srcCount, tgtCount, description, currentLine, pair, editLine, keep,
  }
}
