import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type { AiBomExportSchema } from './assurance-aibom'
import type {
  AllocatedIdentifierSchema,
  DatatypeClassifierInfoSchema,
  DatatypeTypeCatalogSchema,
  DatatypeTypeUsageSchema,
  DatatypeTypeUsagesSchema,
  DiagramRefListSchema,
} from './diagram-types'
import type { DirectNeighborhoodSchema, EntityContextSchema } from './entities'
import type { DocumentListSchema } from './documents'
import type {
  ViewpointPersistResultSchema,
  ViewpointPinsSchema,
  ViewpointReferencerListSchema,
  ViewpointValidationIssueSchema,
} from './viewpoints'
import type { WriteHelpSchema } from './server'

/**
 * The response schemas that had no type-level assertion, now that they do.
 *
 * `contractCoverage.test.ts` measured the gap; this closes most of it. Every one of these was
 * expected to surface drift and eight did — which is the argument for the measurement. Read the
 * mismatch before choosing a side: "the server owns the contract" means *what the server produces*,
 * not what its DTO says, and in six of the eight the DTO was wrong about its own producer.
 *
 * What each one found, for the record:
 *
 * * `DocumentSummary.group` — client `optional`, DTO required with no default, so the route would
 *   500 rather than omit it. The client was the permissive side.
 * * `EntityContextResponse.connections` — declared `dict[str, list[…]]`, published as an object with
 *   arbitrary string keys, for a set of exactly three. Closed, in the application read model that
 *   decides the grouping and in the DTO that mirrors it.
 * * `EntityContextResponse.etag`/`generation` — `| None = None` published two fields as optional
 *   that `EntityContextReadModel` types as required, on a route with `exclude_none=True`, so a None
 *   would have been dropped from the body whose purpose is to say which snapshot it came from.
 * * `ViewpointPersistResponse.version` — same shape: `as_answer` emits the key unconditionally.
 * * `ViewpointValidationIssueDto.expected`/`found` — the DTO's own docstring says both are always
 *   serialised; the defaults published them as optional, contradicting it.
 * * `DiagramReferenceListResponse` — the client's envelope existed only as an anonymous
 *   `Schema.Struct` inside the adapter, so nothing could hold it against the document.
 * * `WriteHelpResponse.entity_type_catalog` — required in the document, `optional` in the client.
 * * `MatrixPreviewResponse` — the route declared the mutation envelope and returned `{markdown}`,
 *   answering 500 to every caller. Asserted in `openapi.contract.diagrams.test-d.ts`.
 */

describe('assurance exports', () => {
  it('decodes an AI-BOM export', () => {
    expectTypeOf<SchemaType<typeof AiBomExportSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomExportResponse']>
    >()
  })
})

describe('diagram-type catalogues', () => {
  it('decodes an allocated identifier', () => {
    expectTypeOf<SchemaType<typeof AllocatedIdentifierSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AllocatedIdentifierResponse']>
    >()
  })

  it('decodes the datatype classifier catalogue, and one classifier', () => {
    expectTypeOf<SchemaType<typeof DatatypeTypeCatalogSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeListResponse']>
    >()
    expectTypeOf<SchemaType<typeof DatatypeClassifierInfoSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeClassifierInfo']>
    >()
  })

  it('decodes where a classifier type is used', () => {
    expectTypeOf<SchemaType<typeof DatatypeTypeUsagesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeUsageResponse']>
    >()
    expectTypeOf<SchemaType<typeof DatatypeTypeUsageSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeUsage']>
    >()
  })

  it('decodes which diagrams draw a pair', () => {
    expectTypeOf<SchemaType<typeof DiagramRefListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramReferenceListResponse']>
    >()
  })
})

describe('entity reads', () => {
  it('decodes an entity with its connection context', () => {
    expectTypeOf<SchemaType<typeof EntityContextSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityContextResponse']>
    >()
  })

  it('decodes a direct neighbourhood, and the hop map inside it', () => {
    expectTypeOf<SchemaType<typeof DirectNeighborhoodSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DirectNeighborhood']>
    >()
  })
})

describe('documents', () => {
  it('decodes a page of documents, and one row', () => {
    expectTypeOf<SchemaType<typeof DocumentListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentListResponse']>
    >()
  })
})

describe('viewpoint authoring', () => {
  it('decodes a persist outcome, its issues and its referencers', () => {
    expectTypeOf<SchemaType<typeof ViewpointPersistResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointPersistResponse']>
    >()
  })

  it('decodes one validation finding', () => {
    expectTypeOf<SchemaType<typeof ViewpointValidationIssueSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointValidationIssueDto']>
    >()
  })

  it('decodes the diagrams and matrices that pin a viewpoint', () => {
    expectTypeOf<SchemaType<typeof ViewpointReferencerListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointReferencerListResponse']>
    >()
  })

  it('decodes the pin list', () => {
    expectTypeOf<SchemaType<typeof ViewpointPinsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointPinsResponse']>
    >()
  })
})

describe('write help', () => {
  /**
   * The client reads two of the response's ten fields, and one of those only for its `prefix`.
   *
   * So the oracle is a *named projection* of the document rather than the whole component. Plain
   * equality would fail for a narrowing that is not drift, and an exception in
   * `UNASSERTED_SCHEMAS` would give up strictness on the fields the client does read — which is
   * exactly how the one real divergence here survived.
   */
  type CatalogEntry = Pick<components['schemas']['EntityTypeCatalogEntry'], 'prefix'>
  type WriteHelpRead = {
    entity_types_by_domain: components['schemas']['WriteHelpResponse']['entity_types_by_domain']
    entity_type_catalog: { [key: string]: CatalogEntry }
  }

  it('decodes the slice of the write-help catalogue it reads', () => {
    expectTypeOf<SchemaType<typeof WriteHelpSchema>>().toEqualTypeOf<Immutable<WriteHelpRead>>()
  })
})
