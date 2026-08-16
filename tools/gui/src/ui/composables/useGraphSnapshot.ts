import { ref } from 'vue'
import {
  downloadBlob, rasterise, snapshotFilename, snapshotSvgMarkup, type SnapshotFrame,
} from '../lib/graphSnapshot'

/** What a snapshot is taken of: the live drawing, and the frame it is being read through. */
interface SnapshotSource {
  svgEl: SVGSVGElement | null | undefined
  frame: SnapshotFrame | null | undefined
}

/**
 * A picture of the graph as it stands, in the format asked for.
 *
 * Of the *current frame*, so it is what the reader is looking at rather than everything loaded —
 * zooming in and taking a snapshot is how a reader captures a part of a graph too large to show at
 * once. Failures surface as state rather than throwing: a snapshot that cannot be taken is a
 * disappointment, not an error state for the graph.
 *
 * The source is read at the moment of the snapshot, not captured when this is created — the canvas
 * mounts after the view that owns it, so anything bound earlier would be bound to nothing.
 */
export function useGraphSnapshot(sourceOf: () => SnapshotSource | null, nameOf: () => string) {
  const snapshotError = ref<string | null>(null)

  const takeSnapshot = async (format: 'svg' | 'png'): Promise<void> => {
    snapshotError.value = null
    const source = sourceOf()
    if (!source?.svgEl || !source.frame) return
    const markup = snapshotSvgMarkup(source.svgEl, source.frame)
    try {
      const blob = format === 'svg'
        ? new Blob([markup], { type: 'image/svg+xml;charset=utf-8' })
        : await rasterise(markup, source.frame)
      downloadBlob(blob, snapshotFilename(nameOf(), format, new Date()))
    } catch (cause) {
      snapshotError.value = cause instanceof Error ? cause.message : String(cause)
    }
  }

  return { snapshotError, takeSnapshot }
}
