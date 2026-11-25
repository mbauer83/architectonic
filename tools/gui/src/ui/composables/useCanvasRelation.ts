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
import { relationsDrawn } from '../../domain/layout/canvasComposition'
import { connectionTypeLabel } from '../../domain/connectionTypeLabel'
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
      const drawn = relationsDrawn(context(), editing.session.state.value)
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

  /**
   * The drawn relation at *index* as the session has it: its record, the label this diagram states on it,
   * and its description and multiplicities with any pending edit over the model's. Null for a line that
   * draws no relation of the context read.
   */
  const drawnLine = (index: number) => {
    const row = editing.session.geometry.value?.relations.find((r) => r.index === index)
    const record = row && context().connections.find((c) => c.edge_key === row.key)
    if (!row || !record) return null
    const pending = editing.session.state.value
    const prior: unknown = context().diagram.extra?.connections
    const stored = Array.isArray(prior) ? prior.filter(isRecord) : []
    const overlay = [...stored, ...(pending?.overlays ?? [])].reverse()
      .find(r => stableConnectionId(String(r.artifact_id ?? r.connection_id)) === row.key)
    const stated = overlay?.label ?? record.edge_label_override
    const edit = pending?.commands?.find(c => c.artifact_id === record.artifact_id && c.op === 'model.relation.edit')
    const edited = edit && 'src_multiplicity' in edit ? edit : null
    return {
      row, record, label: typeof stated === 'string' ? stated : '',
      description: edited?.description ?? record.content_text,
      src: edited?.src_multiplicity ?? record.src_multiplicity ?? '',
      tgt: edited?.tgt_multiplicity ?? record.tgt_multiplicity ?? '',
    }
  }

  /** The drawn relation at *index*, read back with its stated label and any pending edit over the model's. */
  const editLine = (index: number) => {
    const line = drawnLine(index)
    if (!line) return
    ends.source.value = line.row.source
    ends.target.value = line.row.target
    currentLine.value = line.record.artifact_id
    options.value = [line.record.conn_type]
    kind.value = line.record.conn_type
    drawing.value = ''
    inModel.value = []
    label.value = line.label
    description.value = line.description
    srcCount.value = line.src
    tgtCount.value = line.tgt
    opened()
  }

  /**
   * The label of the drawn relation at *index*, to be typed in place (02·5): the relation, its sentence,
   * the label this diagram states, and its multiplicities, which are drawn before the label and are not
   * part of it. Null for a line that draws no relation of the context read.
   */
  const labelOf = (index: number) => {
    const line = drawnLine(index)
    return line && {
      id: line.record.artifact_id, text: line.label,
      sentence: `${line.record.source_name} — ${connectionTypeLabel(line.record.conn_type)} → ${line.record.target_name}`,
      multiplicity: line.src || line.tgt ? `${line.src || '·'} → ${line.tgt || '·'}` : '',
    }
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
    options, inModel, drawing, kind, label, srcCount, tgtCount, description, currentLine, pair, editLine, keep, labelOf,
  }
}
