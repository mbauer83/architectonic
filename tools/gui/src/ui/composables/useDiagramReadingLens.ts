import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { ModelService } from '../../application/ModelService'
import type { DiagramAttributePanel } from '../../domain/schemas/diagrams'
import {
  EMPTY_READING_LENS, isEmptyLens, offersAnything, panelOffers, type ReadingLens,
} from '../../domain/readingLens'
import { sanitizeDiagramSvg } from '../lib/svgSanitize'
import { useQuery } from './useQuery'
import type { RepoError } from '../../ports/repositoryErrors'

/**
 * One diagram's picture and how it is being read.
 *
 * The lens, what the reader can be offered, and the rendered SVG — together, because the three are one
 * behaviour. Deciding *when* to re-render is the same decision as owning the query it renders into: a
 * composable that watched the lens and then reached into a query the view held would leave the view
 * holding half a rule, which is how the initial load and the lensed reload come to disagree.
 *
 * A composable rather than lines in the view, for the reason the pan-zoom and the SVG selection are:
 * `DiagramDetailView` is at the source-length limit and this is a whole behaviour, not a few refs.
 *
 * **The lens lives here and nowhere else.** Not the route, not browser storage. The decision about this
 * feature is that a reading is momentary — it lasts a visit to the page — and both of those
 * alternatives would outlive the visit, turning a situative reading into a preference that follows the
 * reader to the next diagram. It is forgotten when the diagram changes for the same reason:
 * `risk_score` on one picture says nothing about the next.
 */
export interface DiagramReading {
  readonly lens: Ref<ReadingLens>
  /** What this diagram can be read by, or `null` until it has been asked for. */
  readonly panel: ComputedRef<DiagramAttributePanel | null>
  /** Whether the panel has anything to offer at all, so a caller knows whether to draw it.
   *
   * Read through `panelOffers`, the one place that answers what an offer holds — the panel's own
   * header asks the same question to say what can be adjusted, and the two used to answer it with
   * separate condition lists. False while the offer is still loading, so the panel appears when it
   * has something to say. */
  readonly offersAnything: ComputedRef<boolean>
  /** The rendered picture, sanitized for `v-html`, or `null` while there is none. */
  readonly svgHtml: ComputedRef<string | null>
  readonly loading: ComputedRef<boolean>
  readonly errorMessage: ComputedRef<string | null>
  /** Whether a render now in flight is a *lensed* one, so a caller can say "rendering…" for an
   * adjustment without saying it for the first plain load. */
  readonly adjusting: ComputedRef<boolean>
  /** Draw this diagram and ask what it can be read by. Called once its type is known. */
  readonly begin: () => void
  /** Forget the picture, before another diagram's arrives. */
  readonly reset: () => void
}

export const useDiagramReadingLens = (options: {
  svc: ModelService
  diagramId: ComputedRef<string>
  /** Whether this diagram is drawn at all — a matrix has no picture to colour. */
  drawn: () => boolean
}): DiagramReading => {
  const { svc, diagramId, drawn } = options
  const picture = useQuery<string, RepoError>()
  const offer = useQuery<DiagramAttributePanel, RepoError>()
  const lens = ref<ReadingLens>(EMPTY_READING_LENS)
  const render = (next: ReadingLens) => picture.run(svc.getDiagramSvg(diagramId.value, next))

  // A lens change *is* a re-render, because there is nothing else it could be: the colouring and the
  // printed values are in the PlantUML body, so the server draws the picture the reader asked for and
  // the browser receives it like any other. The previous picture stays on screen while it runs —
  // replacing it with a spinner would make every adjustment lose the reader's place in the diagram.
  watch(lens, (next) => {
    if (drawn()) render(next)
  })

  watch(diagramId, () => {
    lens.value = EMPTY_READING_LENS
    offer.reset()
  })

  return {
    lens,
    panel: computed(() => offer.data.value ?? null),
    offersAnything: computed(() => offersAnything(panelOffers(offer.data.value ?? null))),
    svgHtml: computed(() => (picture.data.value ? sanitizeDiagramSvg(picture.data.value) : null)),
    loading: computed(() => picture.loading.value),
    errorMessage: computed(() => picture.errorMessage.value),
    adjusting: computed(() => picture.loading.value && !isEmptyLens(lens.value)),
    begin: () => {
      render(lens.value)
      offer.run(svc.getDiagramAttributePanel(diagramId.value))
    },
    reset: picture.reset,
  }
}
