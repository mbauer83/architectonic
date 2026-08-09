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
  /** The first classification level. Chosen before a type, and derived from the type once one is —
   * which is what the canvas colours a note by, at either level. */
  domain: Schema.optional(Schema.String),
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
  /** What the frame declares it holds. `permitted-element-types` is *derived* from these by the
   * server against the current ontology, which is why a frame names a domain rather than a list of
   * types: the declaration keeps meaning the same thing when the ontology gains one. */
  'permitted-domains': Schema.optional(Schema.Array(Schema.String)),
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

/** One selected note or link, and what a lift would do with it. */
export const LiftItemSchema = Schema.Struct({
  kind: Schema.Literal('element', 'document', 'connection', 'reference'),
  id: Schema.String,
  outcome: Schema.Literal('create', 'skip', 'refuse'),
  label: Schema.String,
  'artifact-type': Schema.String,
  /** What a skipped note already is, so the dialog names it rather than saying "already done". */
  'artifact-id': Schema.String,
  code: Schema.String,
  reason: Schema.String,
  /** A narrowing (W128/W129): reported and passed, because the relation exists. */
  warning: Schema.String,
  /** The project this lands in — the target of the frame the note sits in. */
  target: Schema.String,
})
export type LiftItem = typeof LiftItemSchema.Type

/** A link with one end in the selection and one end out — a decision, not an error. */
export const OutsideSelectionSchema = Schema.Struct({
  'link-id': Schema.String,
  'note-id': Schema.String,
  'note-title': Schema.String,
})

/** The preflight, and what the execution did if it ran.
 *
 * One shape for both, because they are one operation: a plan that could only be executed by a
 * second call would be a plan made against a scratchpad that may have moved on.
 */
export const LiftTargetSchema = Schema.Struct({
  group: Schema.String,
  'meta-ontology': Schema.String,
  exists: Schema.Boolean,
})

export const ScratchpadLiftSchema = Schema.Struct({
  /** One per frame that has something in it: the frames are work archetypes, so a canvas routinely
   * holds work for more than one project. */
  targets: Schema.optional(Schema.Array(LiftTargetSchema)),
  items: Schema.optional(Schema.Array(LiftItemSchema)),
  'outside-selection': Schema.optional(Schema.Array(OutsideSelectionSchema)),
  refusal: Schema.String,
  blocks: Schema.Boolean,
  'dry-run': Schema.Boolean,
  committed: Schema.Boolean,
  realized: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  errors: Schema.optional(Schema.Array(Schema.String)),
  'operation-id': Schema.String,
})
export type ScratchpadLift = typeof ScratchpadLiftSchema.Type
