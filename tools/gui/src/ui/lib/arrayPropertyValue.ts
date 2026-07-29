/**
 * The array attribute value as a list editor sees it. The wire form is a JSON-array string
 * (what the write API and the Properties table store); the editor works on a `string[]` of
 * per-item lexical values. Keeping parse/serialize/mutate here — pure and total — lets the
 * component stay a thin view and the behaviour be unit-tested without mounting.
 */
import type { EntityAttributeItemDescriptor } from '../../domain'

/** Parse a stored JSON-array string into per-item lexical strings. A blank or non-array
 * value is an empty list (never throws — a half-typed value must not blank the editor). */
export const parseArrayValue = (raw: string): string[] => {
  const trimmed = raw.trim()
  if (!trimmed) return []
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (!Array.isArray(parsed)) return []
    return parsed.map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
  } catch {
    return []
  }
}

/** Serialize per-item lexical strings back to the stored JSON-array string, typing each item
 * by the item descriptor (numbers/booleans become JSON scalars; everything else a string).
 * An empty list serializes to `""` so an untouched optional array stays absent, not `"[]"`. */
export const serializeArrayValue = (items: string[], descriptor?: EntityAttributeItemDescriptor): string => {
  const kept = items.filter((item) => item.trim() !== '')
  if (kept.length === 0) return ''
  const type = descriptor?.type
  const encoded = kept.map((item) => {
    if (type === 'integer' || type === 'number') {
      const n = Number(item)
      return Number.isNaN(n) ? item : n
    }
    if (type === 'boolean') return item === 'true'
    return item
  })
  return JSON.stringify(encoded)
}

export const addItem = (items: string[], value = ''): string[] => [...items, value]

export const removeItem = (items: string[], index: number): string[] =>
  items.filter((_, i) => i !== index)

/** Move the item at `index` by `delta` (−1 up, +1 down), clamped — a no-op at the ends. */
export const moveItem = (items: string[], index: number, delta: number): string[] => {
  const target = index + delta
  if (target < 0 || target >= items.length) return items
  const next = [...items]
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved)
  return next
}
