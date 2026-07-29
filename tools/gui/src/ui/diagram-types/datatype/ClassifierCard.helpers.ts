import type { AttrTypeRef, Classifier } from './useDatatypeModel'

export type TypeOptionGroup = 'Primitives' | 'This diagram' | 'Engagement' | 'Enterprise'

export interface CatalogClassifier {
  readonly type_id: string
  readonly label: string
  readonly scope: string
  readonly host_diagram_id: string
}

export interface TypeOption {
  readonly key: string
  readonly label: string
  readonly group: TypeOptionGroup
  readonly ref: AttrTypeRef
}

export function optionKey(ref: AttrTypeRef | undefined): string {
  if (!ref) return ''
  return ref.kind === 'primitive' ? `primitive:${ref.name}` : `classifier:${ref.id}`
}

export function refFromOptionKey(key: string, options: readonly TypeOption[]): AttrTypeRef | undefined {
  return options.find((option) => option.key === key)?.ref
}

export function buildTypeOptions(
  primitiveTypes: readonly string[],
  localClassifiers: readonly Classifier[],
  catalogClassifiers: readonly CatalogClassifier[],
  diagramId: string,
): TypeOption[] {
  const options: TypeOption[] = []
  const seen = new Set<string>()
  const append = (option: TypeOption) => {
    if (seen.has(option.key)) return
    seen.add(option.key)
    options.push(option)
  }
  primitiveTypes.forEach((name) => append({
    key: `primitive:${name}`,
    label: name,
    group: 'Primitives',
    ref: { kind: 'primitive', name },
  }))
  localClassifiers.forEach((classifier) => append({
    key: `classifier:${classifier.id}`,
    label: classifier.label ?? classifier.id,
    group: 'This diagram',
    ref: { kind: 'classifier', id: classifier.id },
  }))
  catalogClassifiers.forEach((classifier) => append({
    key: `classifier:${classifier.type_id}`,
    label: classifier.label,
    group: classifier.host_diagram_id === diagramId
      ? 'This diagram'
      : classifier.scope === 'enterprise' ? 'Enterprise' : 'Engagement',
    ref: { kind: 'classifier', id: classifier.type_id },
  }))
  return options
}

/** Resolve an attribute id to its current name (falls back to the id). */
export function attrLabel(id: string, attributes: readonly { id: string; name: string }[]): string {
  return attributes.find((a) => a.id === id)?.name ?? id
}

/** Append an id to an ordered list iff not already present (no repetition). */
export function appendMember(list: readonly string[], id: string): string[] {
  return list.includes(id) ? [...list] : [...list, id]
}

export function removeAt<T>(list: readonly T[], index: number): T[] {
  return list.filter((_, i) => i !== index)
}

/** Swap the element at `index` with its neighbour `delta` away (clamped: no-op at the ends). */
export function moveInList<T>(list: readonly T[], index: number, delta: number): T[] {
  const next = [...list]
  const target = index + delta
  if (target < 0 || target >= next.length) return next
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}
