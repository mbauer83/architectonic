/**
 * The relation a canvas popover drafts: a new one between two elements, its type from what the ontology
 * permits between them, or a drawn one read back for editing — its stated label, and any edit already
 * pending in the session over what the model holds. Kept is a model change proposed to the session.
 */
import { ref, type ComputedRef, type Ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { DiagramContext } from '../../domain'
import { connectionId, stableConnectionId } from '../../domain/artifactId'
import { isRecord } from '../../domain/records'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import type { DiagramEditing } from './useDiagramEditing'

type Member = { readonly alias: string; readonly id: string; readonly type: string }

export function useCanvasRelation(
  svc: ModelService, editing: DiagramEditing, context: () => DiagramContext,
  members: ComputedRef<readonly Member[]>, ends: { source: Ref<string>; target: Ref<string> },
  opened: () => void, failed: (message: string) => void,
  apply: (command: CanvasCommand, overlay: Record<string, unknown>) => void,
) {
  const options = ref<readonly string[]>([])
  const kind = ref('')
  const label = ref('')
  const srcCount = ref('')
  const tgtCount = ref('')
  const description = ref('')
  const currentLine = ref('')
  const member = (alias: string) => members.value.find((e) => e.alias === alias)

  /** A new relation from the source to *alias*, offered the types the ontology permits between them. */
  const pair = async (alias: string) => {
    const from = member(ends.source.value)
    const to = member(alias)
    if (!from || !to) return
    ends.target.value = alias
    options.value = []
    kind.value = label.value = description.value = srcCount.value = tgtCount.value = currentLine.value = ''
    opened()
    try {
      const permitted = await Effect.runPromise(svc.getOntologyPair(from.type, to.type))
      if (ends.target.value !== alias || ends.source.value !== from.alias) return
      options.value = [...new Set([...permitted.connection_types, ...permitted.symmetric])]
      kind.value = options.value[0] ?? ''
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
    const pending = editing.session.state.value
    const prior = context().diagram.extra?.connections
    const stored = Array.isArray(prior) ? (prior as unknown[]).filter(isRecord) : []
    const overlays = [...stored, ...(pending?.overlays ?? [])]
    const overlay = overlays.reverse().find(r => stableConnectionId(String(r.artifact_id ?? r.connection_id)) === row.key)
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

  return { options, kind, label, srcCount, tgtCount, description, currentLine, pair, editLine, keep }
}
