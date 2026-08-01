import { encodeIdentitySegment as encodeSegment } from '../../domain/identitySegments'
/**
 * The canonical GUI route catalog: templates and the typed builders that spell them.
 *
 * Canonical routes only. There is no old→new mapping here and no redirect table — 0.2.0 is a
 * clean break, and a builder that could still emit the old spelling is the mechanism by which a
 * migration silently does not happen.
 *
 * Why builders rather than template literals at the call sites: an artifact id contains
 * characters that a path segment reads as structure. `#` starts a fragment, so a diagram-local
 * id like `DATATY@….x#Order` loses its tail before the request is ever sent; `.` must **not**
 * be encoded, because ASGI decodes `%2E` back and the two spellings would be different keys in
 * a cache. One place that knows which characters to escape is one place to fix when that
 * changes.
 *
 * This module is delivery-side on purpose. Repository-link *parsing* stays in
 * `src/domain/artifactLinks.ts`; a domain module that emitted Vue paths would invert the
 * dependency direction and make the model layer aware of the router.
 */

/**
 * Segments a collection prefix already spells literally, and which therefore cannot also be read
 * as an identifier. `/assurance/analyses/new/stpa` is the create surface; an analysis whose id
 * were `new` would address the same URL and lose.
 */
const RESERVED_SEGMENTS: ReadonlySet<string> = new Set(['new', 'edit', 'groups', 'query', 'graph'])

/** An identifier that cannot be spelled as a path segment without changing what the URL means. */
export class UnaddressableIdentityError extends Error {
  constructor(readonly id: string) {
    super(`'${id}' cannot be a path segment: a collection route already spells it literally`)
    this.name = 'UnaddressableIdentityError'
  }
}

/**
 * Percent-encode an identifier for use as one path segment.
 *
 * `encodeURIComponent` escapes `#` (to `%23`) and leaves `.`, `-`, `_` and `~` alone, which is
 * exactly the rule: `#` must be escaped or the browser truncates the id, and `.` must not be,
 * because the server decodes `%2E` back to `.` and would then hold a second spelling of one
 * identity. `/` is escaped to `%2F` by the same call, and the server rejects that — slash is
 * outside the identifier grammar, so a would-be id containing one is a malformed id, not a
 * deep path.
 *
 * Throws for an id that collides with a reserved literal segment. Emitting that URL would produce
 * a link that resolves to a different page than the caller asked for, which is worse than failing
 * where the mistake is.
 *
 * The *encoding* is `domain/identitySegments`; what this adds is the reserved-literal guard, which is
 * about this router's own collection routes. The REST surface spells none of those literals beside an
 * identifier, so its adapter uses the unguarded encoder rather than inheriting a rule about the GUI.
 */
export const encodeIdentitySegment = (id: string): string => {
  if (RESERVED_SEGMENTS.has(id)) throw new UnaddressableIdentityError(id)
  return encodeSegment(id)
}

/** Route templates, in Vue Router's `:param` spelling. The SPA fallback mirrors these. */
export const ROUTE_TEMPLATES = {
  entityList: '/entities',
  entityCreate: '/entities/new',
  entityGroups: '/entities/groups',
  entityDetail: '/entities/:artifactId',
  /** One entity's neighbourhood: the exploration anchored on it. */
  entityGraph: '/entities/:artifactId/graph',
  /** The exploration surface with no anchor — a whole population, selected by a viewpoint.
   * Addresses no stored thing, so the viewpoint slug is an operand and stays in the query. */
  graphExplore: '/graph',
  documentList: '/documents',
  documentCreate: '/documents/new',
  documentGroups: '/documents/groups',
  documentDetail: '/documents/:artifactId',
  diagramList: '/diagrams',
  diagramCreate: '/diagrams/new',
  diagramGroups: '/diagrams/groups',
  diagramDetail: '/diagrams/:artifactId',
  diagramEdit: '/diagrams/:artifactId/edit',
  matrixCreate: '/matrices/new',
  matrixEdit: '/matrices/:artifactId/edit',
  viewpointList: '/viewpoints',
  viewpointCreate: '/viewpoints/new',
  viewpointQuery: '/viewpoints/query',
  viewpointEdit: '/viewpoints/:slug/edit',
  viewpointMatrix: '/viewpoints/:slug/matrix',
  viewpointDiagram: '/viewpoints/:slug/diagram',
  assuranceBrowse: '/assurance',
  assuranceAnalysisList: '/assurance/analyses',
  assuranceNodeDetail: '/assurance/nodes/:nodeId',
  assuranceNodeGraph: '/assurance/nodes/:nodeId/graph',
  assuranceAnalysisMethod: '/assurance/analyses/:analysisId/:method',
  assuranceAnalysisCreate: '/assurance/analyses/new/:method',
  assuranceAnalysisDiagram: '/assurance/analyses/:analysisId/diagrams/:diagramType',
  assuranceSecurityFindingsList: '/assurance/security-findings',
  assuranceSecurityFindings: '/assurance/arch-artifacts/:archArtifactId/security-findings',
  assuranceVulnerability: '/assurance/vulnerabilities/:identifier',
  assuranceBaselines: '/assurance/baselines',
  assuranceDiagramList: '/assurance/diagrams',
  assuranceSupplyChain: '/assurance/supply-chain',
} as const

export type RouteTemplateName = keyof typeof ROUTE_TEMPLATES

/** The assurance methods that have their own wizard or projection surface. */
export type AssuranceMethodSurface = 'fmea' | 'stpa' | 'grc' | 'cast' | 'gsn'

const seg = encodeIdentitySegment

export const entityListRoute = (): string => ROUTE_TEMPLATES.entityList
export const entityCreateRoute = (): string => ROUTE_TEMPLATES.entityCreate
export const entityDetailRoute = (artifactId: string): string => `/entities/${seg(artifactId)}`
export const entityGraphRoute = (artifactId: string): string => `/entities/${seg(artifactId)}/graph`
export const graphExploreRoute = (): string => ROUTE_TEMPLATES.graphExplore

export const documentListRoute = (): string => ROUTE_TEMPLATES.documentList
export const documentCreateRoute = (): string => ROUTE_TEMPLATES.documentCreate
export const documentDetailRoute = (artifactId: string): string => `/documents/${seg(artifactId)}`

export const diagramListRoute = (): string => ROUTE_TEMPLATES.diagramList
export const diagramCreateRoute = (): string => ROUTE_TEMPLATES.diagramCreate
export const diagramDetailRoute = (artifactId: string): string => `/diagrams/${seg(artifactId)}`
export const diagramEditRoute = (artifactId: string): string => `/diagrams/${seg(artifactId)}/edit`

export const matrixCreateRoute = (): string => ROUTE_TEMPLATES.matrixCreate
export const matrixEditRoute = (artifactId: string): string => `/matrices/${seg(artifactId)}/edit`

export const viewpointEditRoute = (slug: string): string => `/viewpoints/${seg(slug)}/edit`
export const viewpointMatrixRoute = (slug: string): string => `/viewpoints/${seg(slug)}/matrix`
export const viewpointDiagramRoute = (slug: string): string => `/viewpoints/${seg(slug)}/diagram`

export const assuranceNodeDetailRoute = (nodeId: string): string => `/assurance/nodes/${seg(nodeId)}`
export const assuranceNodeGraphRoute = (nodeId: string): string =>
  `/assurance/nodes/${seg(nodeId)}/graph`

export const assuranceAnalysisListRoute = (): string => ROUTE_TEMPLATES.assuranceAnalysisList

export const assuranceAnalysisMethodRoute = (
  analysisId: string,
  method: AssuranceMethodSurface,
): string => `/assurance/analyses/${seg(analysisId)}/${method}`

/**
 * The create surface for a method. `new` is a literal segment under the analyses collection, so
 * it must not be reachable as an analysis id — the router ranks the static segment higher, and
 * a test asserts that outcome rather than the ranking rule.
 */
export const assuranceAnalysisCreateRoute = (method: AssuranceMethodSurface): string =>
  `/assurance/analyses/new/${method}`

export const assuranceAnalysisDiagramRoute = (analysisId: string, diagramType: string): string =>
  `/assurance/analyses/${seg(analysisId)}/diagrams/${seg(diagramType)}`

export const assuranceSecurityFindingsListRoute = (): string =>
  ROUTE_TEMPLATES.assuranceSecurityFindingsList

export const assuranceSecurityFindingsRoute = (archArtifactId: string): string =>
  `/assurance/arch-artifacts/${seg(archArtifactId)}/security-findings`

export const assuranceVulnerabilityRoute = (identifier: string): string =>
  `/assurance/vulnerabilities/${seg(identifier)}`

/**
 * A connection's identity: the single-segment composite the backend emits as its `artifact_id`.
 *
 * Built here rather than at each call site so the `---`/`@@` joiners are written once. Encoded as a
 * whole, because `@` and `#` inside either endpoint id must be escaped and the joiners must not be.
 */
export const connectionIdentity = (
  source: string,
  target: string,
  connectionType: string,
): string => `${source}---${target}@@${connectionType}`

export const encodeConnectionIdentity = (
  source: string,
  target: string,
  connectionType: string,
): string => seg(connectionIdentity(source, target, connectionType))
