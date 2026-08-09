import type { Layout, Note, Scratchpad } from '../../domain/schemas/scratchpads'

/**
 * Every edit the canvas can make, as a pure function from one document to the next.
 *
 * Separated from `useScratchpadDocument`, which owns the state and the undo history: these are
 * values, that is the machinery over them. It is also what makes the history a sequence of whole
 * documents rather than a sequence of inverses — each of these returns a new document, so undo is
 * a matter of keeping the previous one.
 *
 * Each mirrors an aggregate rule the server enforces. Mirroring rather than duplicating: the
 * server is authoritative and refuses anything these get wrong, and doing it here as well is what
 * keeps the canvas from rendering a state the next save will reject.
 */

/** A copy without the named keys.
 *
 * The wire shapes are optional-key rather than nullable, so *removing* a field is how the client
 * says "not set" — a `null` would fail the decoder. Written once because it was written eleven
 * times.
 */
function without<T extends Record<string, unknown>>(record: T, ...keys: readonly (keyof T & string)[]): T {
  const copy = { ...record }
  for (const key of keys) delete copy[key]
  return copy
}

/** The document as the replace endpoint wants it: content without the two derived fields.
 *
 * `group` is where the file sits, which the body carries separately, and each note's `area` is
 * computed by the server from geometry — sending either back would be the client asserting
 * something it does not own. */
export function toReplacePayload(scratchpad: Scratchpad): Record<string, unknown> {
  return {
    ...without(scratchpad, 'group'),
    // `verdict` goes too: the server derives it from an ontology that may have moved on, so
    // sending it back would be the client asserting an answer it does not own.
    notes: (scratchpad.notes ?? []).map((note) => without(note, 'area')),
    links: (scratchpad.links ?? []).map((link) => without(link, 'verdict')),
  }
}

/** Place a note, returning a new document. Position is snapped server-side too; snapping here as
 * well keeps the canvas and the stored value identical, so a save does not visibly nudge a note. */
export function withNoteAt(scratchpad: Scratchpad, noteId: string, x: number, y: number): Scratchpad {
  const grid = 5
  const snap = (value: number): number => Math.round(value / grid) * grid
  const layout: Layout = scratchpad.layout ?? {}
  return {
    ...scratchpad,
    layout: { ...layout, notes: { ...(layout.notes ?? {}), [noteId]: [snap(x), snap(y)] } },
  }
}

export function withNote(scratchpad: Scratchpad, note: Note): Scratchpad {
  const others = (scratchpad.notes ?? []).filter((existing) => existing.id !== note.id)
  return { ...scratchpad, notes: [...others, note] }
}

/** Which frame a point falls in — the **smallest** containing one, tie-broken on id.
 *
 * The one rule here that mirrors a *derivation* rather than a refusal, and it is asked before the
 * note exists: the canvas menu offers what an area permits, which cannot wait for the server to
 * answer `area` on the next read. `Scratchpad.area_of` in the domain is authoritative and decides
 * it exactly this way — smallest by geometry, never by declaration order, because the file is
 * written in stable id order and a note would otherwise change frames merely by being saved.
 */
export function areaAtPoint(scratchpad: Scratchpad, x: number, y: number): string {
  const rects = scratchpad.layout?.areas ?? {}
  const containing = (scratchpad.areas ?? [])
    .flatMap((area) => {
      const rect = rects[area.id]
      const inside = !!rect
        && x >= rect[0] && x <= rect[0] + rect[2]
        && y >= rect[1] && y <= rect[1] + rect[3]
      return inside ? [{ id: area.id, size: rect[2] * rect[3] }] : []
    })
    .sort((a, b) => (a.size - b.size) || a.id.localeCompare(b.id))
  return containing[0]?.id ?? 'unfiled'
}

/** Tie a note to an entity that already exists.
 *
 * The type comes from the entity, not from the note — the entity is the authority on what it is,
 * and the server refuses a reference without one. Binding is the fastest path into a repository
 * that is not empty: reaching for what exists beats inventing a duplicate.
 */
export function withBinding(
  scratchpad: Scratchpad,
  noteId: string,
  entity: { artifact_id: string; artifact_type: string },
): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note) return scratchpad
  // One entity, one note: two would render the same element twice and lift as one.
  const alreadyBound = (scratchpad.notes ?? []).some(
    (other) => other.id !== noteId && other['model-ref']?.['artifact-id'] === entity.artifact_id,
  )
  if (alreadyBound) return scratchpad
  return withNote(scratchpad, {
    ...note,
    destination: 'element',
    'element-type': entity.artifact_type,
    'model-ref': { 'artifact-id': entity.artifact_id, kind: 'bound' },
  })
}

/** Release a binding: the entity is untouched, and the note keeps the title that was its own. */
export function withoutBinding(scratchpad: Scratchpad, noteId: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note || note['model-ref']?.kind !== 'bound') return scratchpad
  return withNote(
    scratchpad,
    without(
      { ...note, destination: 'undecided' as const },
      'domain', 'element-type', 'specialization', 'model-ref',
    ),
  )
}

/** Narrow a note to a domain — the first rung, before any type is chosen.
 *
 * Choosing a domain drops a type that was already set: narrowing runs one level at a time, and
 * re-answering the coarser question re-opens the finer one rather than leaving a type the new
 * domain may not contain.
 */
export function withDomain(scratchpad: Scratchpad, noteId: string, domain: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note || note['model-ref']) return scratchpad
  return withNote(scratchpad, {
    ...without(note, 'element-type', 'specialization', 'document-type'),
    destination: 'element',
    domain,
  })
}

/** Give a note the body that becomes the entity's summary when it is lifted. */
export function withBody(scratchpad: Scratchpad, noteId: string, body: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  return note ? withNote(scratchpad, { ...note, body }) : scratchpad
}

/** Narrow a note to an element type. Refused server-side on a note tied to the model, so the
 * panel does not offer it there either. */
export function withType(scratchpad: Scratchpad, noteId: string, elementType: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note || note['model-ref']) return scratchpad
  return withNote(scratchpad, { ...note, destination: 'element', 'element-type': elementType })
}

/** Send a note to a document instead of an element.
 *
 * The other destination, and the one most of portfolio work actually produces: which projects
 * exist, what they cost and when they land is prose and figures rather than ArchiMate elements.
 * Mutually exclusive with an element type, which the aggregate enforces and this mirrors by
 * dropping it rather than leaving both set.
 */
export function withDocumentType(
  scratchpad: Scratchpad, noteId: string, documentType: string,
): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note || note['model-ref']) return scratchpad
  return withNote(scratchpad, {
    ...without(note, 'element-type', 'specialization'),
    destination: 'document',
    'document-type': documentType,
  })
}

/** Take a note's type away.
 *
 * Every link touching it loses its connection type too: a typed link with an untyped end is a
 * claim nothing supports, and the server would reject the document that asserted it. */
export function withoutType(scratchpad: Scratchpad, noteId: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note || note['model-ref']) return scratchpad
  const untyped = without(
    { ...note, destination: 'undecided' as const },
    'domain', 'element-type', 'specialization', 'document-type',
  )
  return {
    ...withNote(scratchpad, untyped),
    links: (scratchpad.links ?? []).map((link) =>
      link.source === noteId || link.target === noteId
        ? without(link, 'connection-type', 'verdict')
        : link,
    ),
  }
}

/** Drop a realization, leaving the entity where it is — the only thing a note may do about a lift
 * it no longer claims, since the scratchpad never retracts model content. */
export function withoutRealization(scratchpad: Scratchpad, noteId: string): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (note?.['model-ref']?.kind !== 'realized') return scratchpad
  return withNote(scratchpad, without(note, 'model-ref'))
}

/** Swap a link's ends. The remedy that leads when the reverse triple is the permitted one. */
export function withReversedLink(scratchpad: Scratchpad, linkId: string): Scratchpad {
  return {
    ...scratchpad,
    links: (scratchpad.links ?? []).map((link) =>
      link.id === linkId ? { ...link, source: link.target, target: link.source } : link,
    ),
  }
}

export function withLinkType(scratchpad: Scratchpad, linkId: string, connectionType: string): Scratchpad {
  return {
    ...scratchpad,
    links: (scratchpad.links ?? []).map((link) =>
      link.id === linkId ? { ...link, 'connection-type': connectionType } : link,
    ),
  }
}

/** Take a link's relation away, leaving the link drawn.
 *
 * The counterpart of `withoutType` for a note, and it was missing: choosing "Undecided" set the
 * type to the empty string instead, which is not "not set" — the wire shape is optional-key, so a
 * removal is expressed by dropping the key, and an empty one would have been written to the file
 * as a relation with no name. The verdict goes with it: it answered a question no longer asked.
 */
export function withoutLinkType(scratchpad: Scratchpad, linkId: string): Scratchpad {
  return {
    ...scratchpad,
    links: (scratchpad.links ?? []).map((link) =>
      link.id === linkId ? without(link, 'connection-type', 'verdict') : link,
    ),
  }
}

/** Rub out a link, leaving both notes where they are.
 *
 * A scratchpad is for thinking, and thinking includes deciding that two things are not related
 * after all. Nothing here reaches the model: a link that was *realized* into a connection is not
 * retracted by this — the scratchpad never takes model content back, exactly as `withoutRealization`
 * does not delete the entity it stops claiming.
 */
export function withoutLink(scratchpad: Scratchpad, linkId: string): Scratchpad {
  return {
    ...scratchpad,
    links: (scratchpad.links ?? []).filter((link) => link.id !== linkId),
  }
}

export function withoutNote(scratchpad: Scratchpad, noteId: string): Scratchpad {
  const layout: Layout = scratchpad.layout ?? {}
  const notePositions = without(layout.notes ?? {}, noteId)
  return {
    ...scratchpad,
    notes: (scratchpad.notes ?? []).filter((note) => note.id !== noteId),
    // The aggregate deletes a note's links with it; doing the same here means the canvas never
    // shows a link with one end missing while the save is in flight.
    links: (scratchpad.links ?? []).filter((link) => link.source !== noteId && link.target !== noteId),
    layout: { ...layout, notes: notePositions },
  }
}

export function withLink(scratchpad: Scratchpad, id: string, source: string, target: string): Scratchpad {
  const links = scratchpad.links ?? []
  const exists = links.some(
    (link) =>
      (link.source === source && link.target === target)
      || (link.source === target && link.target === source),
  )
  // Drawing the same pair twice is a slip, not a second relation: the canvas would render two
  // curves along one path and neither would be selectable.
  if (exists || source === target) return scratchpad
  return { ...scratchpad, links: [...links, { id, source, target }] }
}
