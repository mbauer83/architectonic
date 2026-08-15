/**
 * A picture of the graph as it currently stands — the arrangement the reader made, not a re-render.
 *
 * The live `<svg>` is cloned and made to stand alone. That works because the canvas draws its
 * appearance as attributes rather than through stylesheets: fills, strokes and dash patterns are
 * bound per element, and the only CSS rules that touch appearance are `:hover` and the selection
 * highlight, neither of which belongs in a snapshot. What does *not* travel is anything inherited
 * from the page — the font above all — so the root carries it explicitly.
 *
 * **Not for signal-styled output.** `/api/viewpoints/export-render` is the only sanctioned way that
 * leaves the browser, because the server burns the computed classification banner into the returned
 * bytes; `stampedRenderExport.ts` is that path and the viewpoint diagram offers it exactly when a
 * signal banner is present. The graph explorer presents no signal banner and so is not that content
 * — but if it ever does, the snapshot must route through the stamped export rather than serialise
 * what is on screen, or the banner is what would be left behind.
 */

import type { ViewBoxRect } from '../components/GraphCanvas.helpers'

/**
 * What the reader sees, framed as they framed it — the canvas's own viewBox type rather than a
 * second name for the same four numbers.
 */
export type SnapshotFrame = ViewBoxRect

const SVG_NS = 'http://www.w3.org/2000/svg'

/** Interactive-only marks: state of the pointer, not of the model. */
const TRANSIENT_CLASSES = ['edge-selected']

/**
 * The live canvas as standalone SVG markup.
 *
 * `width`/`height` in absolute units as well as a `viewBox`, because a bare viewBox has no
 * intrinsic size: pasted into a document or opened alone it would scale to whatever box it landed
 * in, and a rasteriser has nothing to compute a pixel count from.
 */
export const snapshotSvgMarkup = (
  source: SVGSVGElement,
  frame: SnapshotFrame,
  options: { background?: string; fontFamily?: string } = {},
): string => {
  const clone = source.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', SVG_NS)
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
  clone.setAttribute('viewBox', `${frame.x} ${frame.y} ${frame.w} ${frame.h}`)
  clone.setAttribute('width', String(Math.round(frame.w)))
  clone.setAttribute('height', String(Math.round(frame.h)))
  // Inherited from the page in the browser, and from nothing at all in a file.
  clone.setAttribute('font-family', options.fontFamily ?? 'system-ui, sans-serif')
  clone.removeAttribute('style')

  for (const className of TRANSIENT_CLASSES) {
    for (const el of [...clone.querySelectorAll(`.${className}`)]) el.classList.remove(className)
  }

  // Behind everything, and only in the export: on screen the page supplies the ground, and a
  // transparent PNG of dark-on-nothing is a picture of nothing.
  const background = document.createElementNS(SVG_NS, 'rect')
  background.setAttribute('x', String(frame.x))
  background.setAttribute('y', String(frame.y))
  background.setAttribute('width', String(frame.w))
  background.setAttribute('height', String(frame.h))
  background.setAttribute('fill', options.background ?? '#ffffff')
  clone.insertBefore(background, clone.firstChild)

  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(clone)}`
}

/** A filename that says what it is and when it was taken, and sorts by the latter. */
export const snapshotFilename = (label: string, extension: 'svg' | 'png', at: Date): string => {
  const slug = label.replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || 'graph'
  const stamp = at.toISOString().replace(/[:.]/g, '-').replace('T', '_').slice(0, 19)
  return `${slug}_${stamp}.${extension}`
}

/** Hand the bytes to the browser as a download. */
export const downloadBlob = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * Rasterise SVG markup to PNG bytes.
 *
 * At `scale` times the frame, because a snapshot is usually taken to be read later and a graph's
 * labels are small: at 1:1 they are legible only at the size they were on screen.
 *
 * Drawn through an `Image` rather than any library. The markup is self-contained — no external
 * fonts, no remote images — so the canvas it is drawn on stays untainted and `toBlob` is allowed
 * to read it back. A remote reference anywhere in the picture would make that throw, which is one
 * more reason the sprites are inline.
 */
export const rasterise = (markup: string, frame: SnapshotFrame, scale = 2): Promise<Blob> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml;charset=utf-8' }))
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(frame.w * scale))
      canvas.height = Math.max(1, Math.round(frame.h * scale))
      const context = canvas.getContext('2d')
      if (context === null) {
        URL.revokeObjectURL(url)
        reject(new Error('no 2d context'))
        return
      }
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob((blob) => {
        if (blob) resolve(blob)
        else reject(new Error('the canvas produced no PNG'))
      }, 'image/png')
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('the snapshot could not be drawn'))
    }
    image.src = url
  })
