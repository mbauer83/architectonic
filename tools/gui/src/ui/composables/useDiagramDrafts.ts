/**
 * Which drawings on a diagram page are drafts (sketch 03·4, D19, Q17), in both modes. In edit mode the
 * canvas marks them itself (`CanvasDraftMarks`), from the shapes this returns. In view mode the picture
 * is the rendered one, so the same quiet "d" is written into it here, over each draft's drawing in its
 * top right corner — the page's own mark on the picture it shows, never part of what is rendered for a
 * download — and the reader announces the element as a draft (`useDiagramPageReader`).
 */
import { computed, watch, type Ref } from 'vue'
import type { DiagramContext } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import { DRAFT_STATUS, draftAliases } from '../../domain/layout/canvasComposition'
import { pictureExtentOf } from '../lib/svgExtent'
import type { DiagramEditing } from './useDiagramEditing'

const SVG = 'http://www.w3.org/2000/svg'
const MARK = 'data-draft-mark'
/** How far in from the corner the mark sits, and how tall it is, in the picture's own units. */
const INSET = 4
const SIZE = 9

/** Write the mark into the drawing of each draft in *nodes*, after taking out any written before. */
const markPicture = (nodes: ReadonlyMap<string, readonly Element[]>, drafts: ReadonlySet<string>): void => {
  const pictures = new Set([...nodes.values()].flat()
    .flatMap((one) => (one instanceof SVGElement ? [one.ownerSVGElement] : [])))
  for (const picture of pictures) picture?.querySelectorAll(`[${MARK}]`).forEach((mark) => mark.remove())
  for (const [id, drawings] of nodes) {
    if (!drafts.has(stableEntityId(id))) continue
    for (const drawing of drawings) {
      const extent = pictureExtentOf(drawing)
      const holder = drawing.tagName.toLowerCase() === 'g' ? drawing : drawing.parentElement
      if (!extent || !holder) continue
      const mark = document.createElementNS(SVG, 'text')
      mark.setAttribute(MARK, '')
      mark.setAttribute('aria-hidden', 'true')
      mark.setAttribute('x', String(extent.right - INSET))
      mark.setAttribute('y', String(extent.top + INSET + SIZE))
      mark.setAttribute('text-anchor', 'end')
      mark.setAttribute('font-size', String(SIZE))
      mark.setAttribute('style', 'fill: var(--paper-rule); font-family: system-ui, sans-serif; pointer-events: none')
      mark.textContent = 'd'
      holder.appendChild(mark)
    }
  }
}

export function useDiagramDrafts(options: {
  context: Ref<DiagramContext | null>
  editing: DiagramEditing
  /** The rendered picture's drawings, by entity id: what view mode marks. */
  nodeElements: Ref<ReadonlyMap<string, readonly Element[]>>
}) {
  const { context, editing, nodeElements } = options
  /** The entities the model holds as drafts, by stable id. */
  const drafts = computed(() => new Set((context.value?.entities ?? [])
    .filter((one) => one.status === DRAFT_STATUS).map((one) => stableEntityId(one.artifact_id))))
  /** The shapes of the edit canvas that draw a draft, by alias: the model's drafts and the session's. */
  const inEdit = computed((): ReadonlySet<string> => {
    const now = context.value
    return now ? draftAliases(now, editing.session.state.value, editing.session.geometry.value) : new Set()
  })
  watch([nodeElements, drafts], ([nodes, ids]) => markPicture(nodes, ids), { flush: 'post' })
  return { inEdit }
}
