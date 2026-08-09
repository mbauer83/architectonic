import { Schema } from 'effect'

/**
 * The scratchpad wire shapes.
 *
 * Where a field is required here and omitted from the YAML file, that is not a disagreement: the
 * file leaves out what carries no information, and the server resolves each default before it
 * serialises — `body` arrives as `""`, `destination` as `"undecided"`. Making them optional here
 * would leave the decoder looser than the payload, and on a surface where the client writes the
 * whole aggregate back, a field the decoder forgets is a field the next save deletes.
 *
 * Kebab-case keys, deliberately: the response and the file on disk speak one vocabulary, so a
 * person reading a payload and a person reading the YAML are reading the same document. The server
 * derives both from one mapping, and `contracts:check` holds these against the generated types.
 */

const ModelRefSchema = Schema.Struct({
  'artifact-id': Schema.String,
  kind: Schema.Literal('realized', 'bound'),
})

/** What a note has decided to become. `undecided` is where every note starts, and a legitimate
 * place to stay — the feature exists because being asked to decide too early is the wall. */
export const DestinationSchema = Schema.Literal('undecided', 'element', 'document', 'none')
export type Destination = typeof DestinationSchema.Type

export const NoteSchema = Schema.Struct({
  id: Schema.String,
  title: Schema.String,
  body: Schema.String,
  destination: DestinationSchema,
  'element-type': Schema.optional(Schema.String),
  specialization: Schema.optional(Schema.String),
  'document-type': Schema.optional(Schema.String),
  'model-ref': Schema.optional(ModelRefSchema),
  attributes: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  /** Derived server-side from where the note sits. Served rather than recomputed here, so the
   * canvas and the API cannot disagree about which frame owns a note. */
  area: Schema.String,
})
export type Note = typeof NoteSchema.Type

/** What the meta-ontology says about a drawn link.
 *
 * Served with the link rather than fetched per pair: the two-tier split — a refusal at the level
 * relationships are keyed on, a warning at a level that only narrows them — is a property of the
 * ontology's declared classification levels, and deciding it again here would put it in two places.
 */
export const LinkVerdictSchema = Schema.Struct({
  kind: Schema.Literal('unverified', 'reference', 'permitted', 'narrowed', 'refused'),
  code: Schema.String,
  message: Schema.String,
  /** Connection types the ontology permits for this pair, offered as "did you mean one of these". */
  alternatives: Schema.optional(Schema.Array(Schema.String)),
  /** Leads the remedies: dragging an ordered triple the wrong way is the commonest slip there is. */
  'reverse-permitted': Schema.optional(Schema.Boolean),
  'narrowed-by': Schema.optional(Schema.String),
  /** A refusal stops a lift; a narrowing warns and does not. */
  blocks: Schema.optional(Schema.Boolean),
})
export type LinkVerdict = typeof LinkVerdictSchema.Type

export const LinkSchema = Schema.Struct({
  id: Schema.String,
  source: Schema.String,
  target: Schema.String,
  'connection-type': Schema.optional(Schema.String),
  'model-ref': Schema.optional(ModelRefSchema),
  /** Present on a read; never stored, because an ontology may change under a saved scratchpad. */
  verdict: Schema.optional(LinkVerdictSchema),
})
export type Link = typeof LinkSchema.Type

export const AreaSchema = Schema.Struct({
  id: Schema.String,
  label: Schema.String,
  'permitted-element-types': Schema.optional(Schema.Array(Schema.String)),
  'permitted-document-types': Schema.optional(Schema.Array(Schema.String)),
})
export type Area = typeof AreaSchema.Type

export const NoteGroupSchema = Schema.Struct({
  id: Schema.String,
  label: Schema.String,
  members: Schema.optional(Schema.Array(Schema.String)),
})
export type NoteGroup = typeof NoteGroupSchema.Type

/** Geometry, apart from content: rects are `[x, y, w, h]`, points `[x, y]`. */
export const LayoutSchema = Schema.Struct({
  areas: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Array(Schema.Number) })),
  notes: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Array(Schema.Number) })),
  groups: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Array(Schema.Number) })),
})
export type Layout = typeof LayoutSchema.Type

export const ScratchpadSchema = Schema.Struct({
  'artifact-id': Schema.String,
  'artifact-type': Schema.Literal('scratchpad'),
  name: Schema.String,
  description: Schema.String,
  version: Schema.String,
  status: Schema.String,
  group: Schema.String,
  'meta-ontology': Schema.String,
  attributes: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  areas: Schema.optional(Schema.Array(AreaSchema)),
  notes: Schema.optional(Schema.Array(NoteSchema)),
  links: Schema.optional(Schema.Array(LinkSchema)),
  groups: Schema.optional(Schema.Array(NoteGroupSchema)),
  layout: Schema.optional(LayoutSchema),
})
export type Scratchpad = typeof ScratchpadSchema.Type

export const ScratchpadSummarySchema = Schema.Struct({
  'artifact-id': Schema.String,
  name: Schema.String,
  description: Schema.String,
  status: Schema.String,
  version: Schema.String,
  group: Schema.String,
  'meta-ontology': Schema.String,
  'note-count': Schema.Number,
})
export type ScratchpadSummary = typeof ScratchpadSummarySchema.Type

export const ScratchpadListSchema = Schema.Struct({
  scratchpads: Schema.Array(ScratchpadSummarySchema),
})
export type ScratchpadList = typeof ScratchpadListSchema.Type
