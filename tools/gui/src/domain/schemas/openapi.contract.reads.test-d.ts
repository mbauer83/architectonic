import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  DirectNeighborhoodSchema,
  DocumentReferenceSchema,
  EntityContextSchema,
  EntityDetailSchema,
  EntityListSchema,
  EntitySummarySchema,
} from './entities'
import type { DocumentDetailSchema, DocumentListSchema } from './documents'
import type { DiagramListSchema, DiagramSummarySchema } from './diagram-types'
import type {
  ConnectionListResponseSchema,
  ConnectionListSchema,
  ConnectionRecordSchema,
} from './connections'

/**
 * The four busiest reads in the application, held against the published document.
 *
 * These were the largest unasserted shapes in the contract: the entity list and detail, the document
 * detail, the diagram list and the connection list — every one of them on a screen the user opens
 * first. Each carried drift the checked shapes did not:
 *
 * - the entity row declared seven fields no route sends, one of which (`display_alias`) belongs to a
 *   *diagram* read and was the only one anything read;
 * - the entity detail declared `content_html`, which the client renders and no response carries, and
 *   omitted `attributes` while reading `properties` in its place;
 * - the document detail declared `content_text`, `extra` and `is_global` optional against a route
 *   that reads in `full` mode unconditionally, and omitted `group` and `last_updated` entirely;
 * - the connection row declared six always-sent fields optional and omitted `gar_artifact_id`, the
 *   one field that distinguishes a global-artifact proxy from its referent.
 *
 * Two of the mismatches were the *server's*: `record_type` and a document's `artifact_type` were
 * published as `str` where the producer writes a constant, and `display_blocks` as a map of `Any`
 * where `EntityRecord` holds a map of `str`. Those were tightened rather than loosened here — the
 * document owns the contract, so an imprecise declaration is fixed at its source.
 */

describe('the entity list', () => {
  it('decodes the page envelope and the row inside it', () => {
    expectTypeOf<SchemaType<typeof EntityListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityListResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntitySummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntitySummary']>
    >()
  })
})

describe('the entity detail', () => {
  it('decodes the record, its parsed sections and its degree', () => {
    expectTypeOf<SchemaType<typeof EntityDetailSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityDetailResponse']>
    >()
  })

  it('decodes each document that cites the entity', () => {
    expectTypeOf<SchemaType<typeof DocumentReferenceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentReference']>
    >()
  })
})

describe('the document detail', () => {
  it('decodes one document with its content', () => {
    expectTypeOf<SchemaType<typeof DocumentDetailSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentDetailResponse']>
    >()
  })
})

describe('the diagram list', () => {
  it('decodes the page envelope and the row inside it', () => {
    expectTypeOf<SchemaType<typeof DiagramListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramListResponse']>
    >()
    expectTypeOf<SchemaType<typeof DiagramSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramSummary']>
    >()
  })
})

describe('the connection list', () => {
  it('decodes the envelope, the list it wraps and one row', () => {
    // All three, because the adapter unwraps the envelope and hands callers the list: an assertion
    // on the envelope alone would leave the type the *port* speaks in unchecked.
    expectTypeOf<SchemaType<typeof ConnectionListResponseSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionListResponse']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionSummary'][]>
    >()
    expectTypeOf<SchemaType<typeof ConnectionRecordSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionSummary']>
    >()
  })
})

describe('the entity context', () => {
  /**
   * `connections` was `dict[str, list[ContextConnection]]` on the DTO, so the document published "an
   * object with arbitrary string keys" for a set of exactly three — and the decoder, which names all
   * three and no others, could not be compared to it at all. The grouping is decided in the
   * application read model, so that is where it is closed; `ConnectionDirection` is named there too,
   * having previously been a `Literal` in the delivery layer and a bare `str` in the layer that
   * produces it.
   *
   * `etag` and `generation` carried `| None = None`, publishing as optional two fields the read model
   * types as required — on a route with `response_model_exclude_none=True`, so a None would have been
   * dropped from the body whose whole purpose is to say which snapshot it came from.
   */
  it('decodes an entity with its connections grouped by direction', () => {
    expectTypeOf<SchemaType<typeof EntityContextSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityContextResponse']>
    >()
  })
})

describe('the neighbourhood', () => {
  it('decodes a direct neighbourhood, and the hop map inside it', () => {
    expectTypeOf<SchemaType<typeof DirectNeighborhoodSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DirectNeighborhood']>
    >()
  })
})

describe('the document list', () => {
  // `DocumentSummary.group` was `optional` on the client and required with no default on the DTO, so
  // the route would answer 500 rather than omit it. The client was the permissive side.
  it('decodes a page of documents, and one row', () => {
    expectTypeOf<SchemaType<typeof DocumentListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentListResponse']>
    >()
  })
})
