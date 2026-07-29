import type { ViewerSubPartContext } from '../../lib/diagramViewerExtensions'

/**
 * Datatype classifier attribute selection.
 *
 * A classifier's typed attributes render as ordered rows inside its SVG node; the full records
 * (type, multiplicity, key membership, role, provenance) travel in the diagram-context payload's
 * raw diagram-entities. This module turns those rows into selectable sub-parts and shapes the
 * detail payload — all datatype knowledge stays here, out of the generic viewer.
 */
export interface DatatypeAttrType {
  kind?: string
  name?: string
  id?: string
}

export interface DatatypeAttr {
  id?: string
  name: string
  type?: DatatypeAttrType | string
  multiplicity?: string
  optional?: boolean
  default?: string
  role?: string
  provenance?: string
  note?: string
}

export interface ClassifierAttributeInfo {
  label: string
  attributes: DatatypeAttr[]
  identity: string[]
  uniqueKeys: Array<{ name?: string; attribute_ids: string[] }>
}

/** Detail payload handed to AttributeDetailPanel for a selected attribute row. `classifierId` +
 * `attributeId` address the record for a metadata patch (id-based, reorder-safe). */
export interface AttributeDetail {
  classifierId: string
  /** The owning record's entity type — used to resolve its `editable_metadata` config. */
  ownerType: string
  attributeId?: string
  name: string
  typeLabel: string
  multiplicity?: string
  optional: boolean
  default?: string
  role?: string
  provenance?: string
  note?: string
  badges: string[]
  ownerLabel: string
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string') : []
}

function asAttr(value: unknown): DatatypeAttr | null {
  if (typeof value !== 'object' || value === null) return null
  const rec = value as Record<string, unknown>
  return typeof rec.name === 'string' ? (rec as unknown as DatatypeAttr) : null
}

/**
 * Map classifier id → its attribute compartment + key metadata, parsed from raw diagram-entities.
 * Keyed by the classifier's canonical id (which equals the SVG node's resolved data-entity-id for
 * workspace-scoped classifiers).
 */
export function buildClassifierAttributes(
  diagramEntities: unknown,
): Map<string, ClassifierAttributeInfo> {
  const map = new Map<string, ClassifierAttributeInfo>()
  const classifiers = (diagramEntities as { classifier?: unknown } | null)?.classifier
  if (!Array.isArray(classifiers)) return map
  for (const raw of classifiers) {
    if (typeof raw !== 'object' || raw === null) continue
    const rec = raw as Record<string, unknown>
    const id = typeof rec.id === 'string' ? rec.id : null
    if (!id) continue
    const attributes = Array.isArray(rec.attributes)
      ? rec.attributes.map(asAttr).filter((a): a is DatatypeAttr => a !== null)
      : []
    const uniqueKeys = Array.isArray(rec.unique_keys)
      ? rec.unique_keys
          .filter((k): k is Record<string, unknown> => typeof k === 'object' && k !== null)
          .map((k) => ({
            name: typeof k.name === 'string' ? k.name : undefined,
            attribute_ids: asStringList(k.attribute_ids),
          }))
      : []
    const label = typeof rec.label === 'string' ? rec.label : id
    map.set(id, { label, attributes, identity: asStringList(rec.identity), uniqueKeys })
  }
  return map
}

/** Human-readable type label (primitive name, classifier id, or raw string). */
export function attributeTypeLabel(attr: DatatypeAttr): string {
  const t = attr.type
  if (!t) return ''
  if (typeof t === 'string') return t
  if (t.kind === 'classifier') return t.id ?? ''
  return t.name ?? ''
}

/** Key-membership badges: 'identity' and any unique-key the attribute belongs to. */
export function attributeKeyBadges(info: ClassifierAttributeInfo, attrId: string | undefined): string[] {
  if (!attrId) return []
  const badges: string[] = []
  if (info.identity.includes(attrId)) badges.push('identity')
  for (const key of info.uniqueKeys) {
    if (key.attribute_ids.includes(attrId)) badges.push(key.name ? `unique: ${key.name}` : 'unique')
  }
  return badges
}

export function toAttributeDetail(
  info: ClassifierAttributeInfo, attr: DatatypeAttr, classifierId: string,
): AttributeDetail {
  return {
    classifierId,
    ownerType: "classifier",
    attributeId: attr.id,
    name: attr.name,
    typeLabel: attributeTypeLabel(attr),
    multiplicity: attr.multiplicity,
    optional: !!attr.optional,
    default: attr.default,
    role: attr.role,
    provenance: attr.provenance,
    note: attr.note,
    badges: attributeKeyBadges(info, attr.id),
    ownerLabel: info.label,
  }
}

/**
 * Attach attribute-row selection to a classifier node. The class box renders, per attribute in
 * declaration order, a `[data-visibility-modifier]` glyph group immediately followed by a sibling
 * `<text>` label. We bind BOTH (so the whole row — glyph and name — is the click target, not just
 * the small glyph) and report them to the viewer for selected-highlighting. Wiring only happens
 * when the glyph-row count matches the model's attribute count, so a divergent layout never
 * mis-binds. Selectable elements are marked `data-subpart` for the viewer's hover affordance.
 */
export function attachClassifierAttributeRows(ctx: ViewerSubPartContext): void {
  const info = buildClassifierAttributes(ctx.diagramEntities).get(ctx.entityId)
  if (!info || info.attributes.length === 0) return
  const glyphs = Array.from(ctx.node.querySelectorAll<SVGGElement>('g[data-visibility-modifier]'))
  if (glyphs.length !== info.attributes.length) return
  glyphs.forEach((glyph, index) => {
    const attr = info.attributes[index]
    const detail = toAttributeDetail(info, attr, ctx.entityId)
    const label = glyph.nextElementSibling
    const rowEls: Element[] =
      label && label.tagName.toLowerCase() === 'text' ? [glyph, label] : [glyph]
    for (const el of rowEls) {
      el.setAttribute('data-subpart', '')
      el.addEventListener(
        'click',
        (ev) => {
          ev.stopPropagation()
          ctx.onSelect(detail, rowEls)
        },
        { signal: ctx.signal },
      )
    }
  })
}
