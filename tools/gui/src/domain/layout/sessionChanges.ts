/**
 * What a canvas session changed in what the diagram holds and in the model, as the rows of the list Save
 * shows: elements added or drawn again, removed, moved into and out of boxes, and each model command.
 * The arranging is counted separately, against the arrangement (`arrangedUnits`).
 */
import type { CanvasCommand, GroupingIntent } from '../../ports/diagramWriteBodies'
import type { DiagramOccurrence } from '../diagramOccurrences'
import { connectionParts, stableConnectionId } from '../artifactId'
import { connectionTypeLabel } from '../connectionTypeLabel'

/** One row of what Save would write, in the product's words. */
export interface PendingChange {
  readonly key: string
  readonly text: string
  readonly model?: boolean
}

interface Content {
  readonly commands?: readonly CanvasCommand[]
  /** What this diagram states on its relations — a label — each over the one before it. */
  readonly overlays?: readonly Record<string, unknown>[]
  readonly additions?: ReadonlyMap<string, string>
  readonly drawnRelations?: readonly string[]
  readonly occurrences?: readonly DiagramOccurrence[]
  readonly regroupings?: readonly GroupingIntent[]
  readonly removed?: ReadonlySet<string>
}

/**
 * The content rows of *now*. *named* names an instance by its key or entity id, *boxNamed* a box by its
 * grouping id; *drawnBefore* are the aliases the session opened with, so removing what it added is no row.
 */
export const contentChanges = (
  now: Content, drawnBefore: ReadonlySet<string>, named: (alias: string) => string,
  instanceNamed: (key: string) => string, boxNamed: (grouping: string) => string,
): readonly PendingChange[] => {
  /** A relation by its ends' names and its type, read source to target; its id where it is no relation id. */
  const relationNamed = (id: string): string => {
    const parts = connectionParts(id)
    return parts
      ? `${instanceNamed(parts.source)} — ${connectionTypeLabel(parts.type)} → ${instanceNamed(parts.target)}` : id
  }
  const model = (now.commands ?? []).map((c) => ({
    key: `${c.op}:${c.artifact_id}`, model: true,
    text: c.op === 'model.element.create' ? `Create element: ${c.name}`
      : c.op === 'model.element.rename' ? `Rename element: ${c.name}`
        : c.op === 'model.element.delete' ? `Delete from model: ${instanceNamed(c.artifact_id)}`
          : c.op === 'model.element.edit' ? `Edit details: ${instanceNamed(c.artifact_id)}`
            : `${c.op === 'model.relation.edit' ? 'Edit' : 'Create'} relationship: ${relationNamed(c.artifact_id)}`,
  }))
  const added = [
    ...[...now.additions ?? []].map(([id, name]) => ({ key: id, text: `Added to diagram: ${name}` })),
    ...(now.occurrences ?? []).map((one) => ({
      key: one.id, text: `Drawn again: ${instanceNamed(one.backing_entity_id)}`,
    })),
    ...(now.drawnRelations ?? []).map((id) => ({
      key: `drawn:${id}`, text: `Drawn from the model: ${relationNamed(id)}`,
    })),
  ]
  const regrouped = (now.regroupings ?? []).map((intent, at) => ({
    key: `regrouped:${at}`,
    text: `${intent.intent === 'nest' ? `Nested in ${boxNamed(intent.grouping)}` : 'Taken out of its box'}: `
      + intent.keys.map(instanceNamed).join(', '),
  }))
  const removed = [...now.removed ?? []].filter((alias) => drawnBefore.has(alias)).map((alias) => ({
    key: `removed:${alias}`, text: `Removed from the diagram: ${named(alias)} — it stays in the model`,
  }))
  return [...added, ...removed, ...regrouped, ...relabelled(now, relationNamed), ...model]
}

/**
 * The labels a session typed on relations it changes nothing else about (02·5), each relation once with
 * its last label: one that comes with a relation created, edited or drawn is that change's, not a row.
 */
const relabelled = (now: Content, relationNamed: (id: string) => string): readonly PendingChange[] => {
  const accompanied = new Set([
    ...(now.commands ?? []).map((c) => c.artifact_id), ...now.drawnRelations ?? [],
  ].map(stableConnectionId))
  const last = new Map((now.overlays ?? []).flatMap((overlay) => {
    const id = overlay.artifact_id
    return typeof id === 'string' && typeof overlay.label === 'string' && !accompanied.has(stableConnectionId(id))
      ? [[stableConnectionId(id), { id, label: overlay.label }] as const] : []
  }))
  return [...last.values()].map(({ id, label }) => ({
    key: `label:${stableConnectionId(id)}`,
    text: label ? `Label on this diagram: ${relationNamed(id)} — “${label}”`
      : `Label taken off this diagram: ${relationNamed(id)}`,
  }))
}
