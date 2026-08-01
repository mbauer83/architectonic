import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * How much of the response contract is actually pinned to the server's document.
 *
 * The `*.test-d.ts` files assert that a hand-written effect Schema produces exactly the type the
 * generated OpenAPI types declare. Nothing measured how many schemas had such an assertion, so the
 * unasserted ones were invisible: `EntityContextConnectionSchema` carried six wrongly-optional
 * fields for a whole migration and was found only when an assertion was finally written for it.
 * This test is that measurement — every exported `*Schema` is either covered or a named exception
 * with a reason, and the reasons are the remaining work, stated in the source tree.
 *
 * Coverage is **transitive**, because type-level equality is deep. If `DocumentTypeSchema` is
 * asserted and it embeds `FrontmatterFieldSchema`, the embedded schema's type is compared against
 * the document's too — field by field, `null` by `null`. Counting only the schema named in the
 * assertion would demand a redundant second assertion for every leaf and turn the exception table
 * into noise. So assertions seed a root set and coverage flows down the reference graph.
 */

const SCHEMA_DIR = import.meta.dirname

/**
 * Why a schema has no assertion. An empty reason is refused: the point of the table is that a gap
 * costs a sentence explaining it, not a silent line.
 */
const UNASSERTED_SCHEMAS: Readonly<Record<string, string>> = {
  AiBomExportSchema:
    'Remaining work. `AiBomExportResponse` exists in the document; the client shape predates it.',
  AllocatedIdentifierSchema:
    'Remaining work. `AllocatedIdentifierResponse` exists in the document; not yet compared.',
  C4NavLinkSchema:
    'Client-side composite. Assembled by the C4 navigation adapter from a diagram read; no single ' +
    'server component describes it.',
  C4NavigationSchema:
    'Client-side composite, built from `C4NavLinkSchema`; the server sends the diagram, not the nav.',
  DatatypeClassifierInfoSchema:
    'Remaining work. `DatatypeClassifierInfo` exists in the document; not yet compared.',
  DatatypeTypeCatalogSchema:
    'Remaining work. Served under the datatype module`s own extras; the envelope around it is ' +
    'declared, the catalogue inside is not.',
  DatatypeTypeUsageSchema:
    'Remaining work. `DatatypeTypeUsage` exists in the document; not yet compared.',
  DatatypeTypeUsagesSchema:
    'Remaining work. Wraps `DatatypeTypeUsageSchema`; blocked on the same comparison.',
  DiagramConnectionSchema:
    'Remaining work. The preview`s connection row; `DiagramConnectionItem` is its counterpart.',
  DiagramRefSchema:
    'Remaining work. `DiagramReference` exists in the document; not yet compared.',
  DiagramRefsSchema:
    'Remaining work. Wraps `DiagramRefSchema`; blocked on the same comparison.',
  DirectNeighborhoodSchema:
    'Remaining work. The direct arm of the neighbourhood union; `DirectNeighborhood` is its ' +
    'counterpart, and asserting it would carry `NeighborsSchema` with it.',
  DocumentListSchema:
    'Remaining work. `DocumentListResponse` exists in the document; not yet compared.',
  DocumentSummarySchema:
    'Remaining work. Reached only through `DocumentListSchema`; blocked on that comparison.',
  EntityContextSchema:
    'Remaining work. `EntityContextResponse` exists in the document. Its two members — the entity ' +
    'detail and the context connection — are both asserted, so only the envelope is unpinned.',
  NeighborsSchema:
    'Remaining work. The hop map, reached only through `DirectNeighborhoodSchema`; blocked on that ' +
    'comparison.',
  MatrixPreviewResultSchema:
    'Client-side composite. The matrix view folds a diagram read and a config read into one shape ' +
    'the server never sends whole.',
  SyncSaveResultSchema:
    'Remaining work. The save route`s result; served through the write-result envelope, which is ' +
    'asserted, but this narrower shape is not.',
  ViewpointPersistResultSchema:
    'Remaining work. No single component in the document yet describes the persist answer.',
  ViewpointPinsSchema:
    'Remaining work. `ViewpointPinsResponse` exists in the document; not yet compared.',
  ViewpointReferencerListSchema:
    'Remaining work. `ViewpointReferencerListResponse` exists in the document; not yet compared.',
  ViewpointReferencerSchema:
    'Remaining work. Reached only through `ViewpointReferencerListSchema`; blocked on that comparison.',
  ViewpointSummarySchema:
    'Remaining work. The viewpoint list row; served inside catalogues whose envelopes are asserted ' +
    'while the row itself is not.',
  ViewpointValidationIssueSchema:
    'Remaining work. `ViewpointValidationIssueDto` exists in the document; not yet compared.',
  WriteHelpEntityTypeCatalogEntrySchema:
    'Remaining work. Reached only through `WriteHelpSchema`; blocked on that comparison.',
  WriteHelpSchema:
    'Remaining work. `WriteHelpResponse` exists in the document; not yet compared.',
}

// ── Scanning ──────────────────────────────────────────────────────────────────

const isTypeTest = (file: string): boolean => file.endsWith('.test-d.ts')
const isRuntimeTest = (file: string): boolean => file.endsWith('.test.ts')
const isGenerated = (file: string): boolean => file === 'openapi.generated.ts'

const filesMatching = (predicate: (file: string) => boolean): readonly string[] =>
  readdirSync(SCHEMA_DIR)
    .filter((entry) => entry.endsWith('.ts'))
    .filter(predicate)
    .map((entry) => join(SCHEMA_DIR, entry))

const schemaModules = (): readonly string[] =>
  filesMatching((file) => !isTypeTest(file) && !isRuntimeTest(file) && !isGenerated(file))

const typeTests = (): readonly string[] => filesMatching(isTypeTest)

/**
 * Every top-level declaration head, so a declaration's body can be delimited by the next one.
 *
 * Anchored at column zero: a nested `const` inside a schema body is part of that body, not a
 * sibling. Splitting on `*Schema` heads alone would attribute an intervening helper function's
 * references to the schema above it and report coverage that does not exist.
 */
const DECLARATION_HEAD = /^(?:export )?(const|type|function|interface|class|enum|let)\s+(\w+)/gm

const SCHEMA_REFERENCE = /\b(\w*Schema)\b/g

interface ModuleFacts {
  /** Exported `*Schema` constants — the population coverage is measured over. */
  readonly exported: ReadonlySet<string>
  /** Every `*Schema` constant, exported or not, to the other schemas its definition names. */
  readonly references: ReadonlyMap<string, ReadonlySet<string>>
  /** Exported type alias to the schema it is `typeof X.Type` of. */
  readonly aliases: ReadonlyMap<string, string>
}

const readModules = (): ModuleFacts => {
  const exported = new Set<string>()
  const references = new Map<string, Set<string>>()
  const aliases = new Map<string, string>()

  for (const file of schemaModules()) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(
      /^export type (\w+) = typeof (\w*Schema)\.(?:Type|Encoded)/gm,
    )) {
      aliases.set(match[1], match[2])
    }
    for (const match of source.matchAll(/^export const (\w*Schema)\b/gm)) exported.add(match[1])

    const heads = [...source.matchAll(DECLARATION_HEAD)]
    heads.forEach((head, index) => {
      const [, keyword, name] = head
      if (keyword !== 'const' || !name.endsWith('Schema')) return
      const end = heads[index + 1]?.index ?? source.length
      const body = source.slice(head.index, end)
      const named = references.get(name) ?? new Set<string>()
      for (const reference of body.matchAll(SCHEMA_REFERENCE)) {
        if (reference[1] !== name) named.add(reference[1])
      }
      references.set(name, named)
    })
  }
  return { exported, references, aliases }
}

/**
 * The schemas an assertion names directly.
 *
 * Two spellings both count. `SchemaType<typeof XSchema>` names the constant; several assertions
 * instead use the module's exported type alias — `expectTypeOf<ErrorEnvelope>()` — which is the same
 * assertion written through `typeof ErrorEnvelopeSchema.Type`. Reading only the first spelling would
 * report the alias-asserted schemas as gaps.
 */
const assertedRoots = (aliases: ReadonlyMap<string, string>): ReadonlySet<string> => {
  const roots = new Set<string>()
  for (const file of typeTests()) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(/typeof (\w*Schema)\b/g)) roots.add(match[1])
    for (const match of source.matchAll(/expectTypeOf<\s*(\w+)\s*>/g)) {
      const aliased = aliases.get(match[1])
      if (aliased !== undefined) roots.add(aliased)
    }
  }
  return roots
}

const reachableFrom = (
  roots: ReadonlySet<string>,
  references: ReadonlyMap<string, ReadonlySet<string>>,
): ReadonlySet<string> => {
  const covered = new Set<string>()
  const pending = [...roots].filter((root) => references.has(root))
  while (pending.length > 0) {
    const next = pending.pop()
    if (next === undefined || covered.has(next)) continue
    covered.add(next)
    pending.push(...(references.get(next) ?? []))
  }
  return covered
}

const facts = readModules()
const roots = assertedRoots(facts.aliases)
const covered = reachableFrom(roots, facts.references)
const uncovered = [...facts.exported].filter((name) => !covered.has(name)).sort()

// ── The measurement ───────────────────────────────────────────────────────────

describe('type-level response contract coverage', () => {
  it('accounts for every exported schema, as an assertion or a reasoned exception', () => {
    const declared = Object.keys(UNASSERTED_SCHEMAS)
    expect(uncovered.filter((name) => !declared.includes(name))).toEqual([])
  })

  it('carries no stale exception', () => {
    // An exception for a schema that has since been asserted, or renamed away, would make the gap
    // look larger than it is and quietly excuse the next one added under the same name.
    const declared = Object.keys(UNASSERTED_SCHEMAS).sort()
    expect(declared.filter((name) => !facts.exported.has(name))).toEqual([])
    expect(declared.filter((name) => covered.has(name))).toEqual([])
  })

  it('states a reason for each exception', () => {
    const unreasoned = Object.entries(UNASSERTED_SCHEMAS)
      .filter(([, reason]) => reason.trim().length < 20)
      .map(([name]) => name)
    expect(unreasoned).toEqual([])
  })
})

describe('the coverage scanner itself', () => {
  // Without these, a regex that stopped matching would report full coverage over two empty sets —
  // the failure mode that made the gap invisible in the first place.
  it('finds the schema population and the assertions over it', () => {
    expect(facts.exported.size).toBeGreaterThan(200)
    expect(roots.size).toBeGreaterThan(150)
    expect(facts.aliases.size).toBeGreaterThan(100)
  })

  it('resolves an assertion written through a type alias', () => {
    // `errors.ts` asserts `expectTypeOf<ErrorEnvelope>()`, never `typeof ErrorEnvelopeSchema`.
    expect(facts.aliases.get('ErrorEnvelope')).toBe('ErrorEnvelopeSchema')
    expect(covered.has('ErrorEnvelopeSchema')).toBe(true)
    expect(roots.has('ErrorEnvelopeSchema')).toBe(true)
  })

  it('propagates coverage into an embedded schema no assertion names', () => {
    // `FrontmatterFieldSchema` is reached only through `DocumentTypeSchema`, which is asserted.
    expect(facts.references.get('DocumentTypeSchema')?.has('FrontmatterFieldSchema')).toBe(true)
    expect(roots.has('FrontmatterFieldSchema')).toBe(false)
    expect(covered.has('FrontmatterFieldSchema')).toBe(true)
  })

  it('reports a schema outside every assertion`s reach as uncovered', () => {
    // The table above is non-empty, so the uncovered set must be too; a scanner that covered
    // everything would make the stale-exception check fail instead, which is the other direction.
    expect(uncovered.length).toBeGreaterThan(0)
  })
})
