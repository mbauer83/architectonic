import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Every viewer of a rendered diagram has the same window (D13, L10): zoom, pan, the overview, the names
 * written at screen size and the keys. They come together in `DiagramViewportOverlays`, so a component
 * that frames a picture with `useFittedPanZoom` mounts it. The overview was found on one viewer of four
 * (the stored diagram), because each viewer had mounted the controls alone and the overview was added
 * beside them on one page only.
 */

const UI_ROOT = join(import.meta.dirname, '..', '..')

const vueFiles = (directory: string): string[] => readdirSync(directory).flatMap((entry) => {
  const path = join(directory, entry)
  if (statSync(path).isDirectory()) return entry === '__tests__' ? [] : vueFiles(path)
  return path.endsWith('.vue') ? [path] : []
})

describe('a diagram window', () => {
  it('mounts its overlays wherever a picture is framed with useFittedPanZoom', () => {
    const framing = vueFiles(UI_ROOT).filter((path) => /\buseFittedPanZoom\(/.test(readFileSync(path, 'utf8')))
    expect(framing.length).toBeGreaterThan(3)
    const without = framing.filter((path) => !readFileSync(path, 'utf8').includes('<DiagramViewportOverlays'))
    expect(without.map((path) => relative(UI_ROOT, path))).toEqual([])
  })
})
