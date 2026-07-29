import { expect, type Page, type Route } from '@playwright/test'
import { addSyntheticBanner } from './mediaHelpers'

export const BACKEND = 'APP@1777293133.OYEmP1.architecture-backend'
export const SIGNAL_SOURCES = 'APP@1780783993.JqIBPJ.supply-chain-signal-sources'
export const VULNERABILITY_CONNECTOR = 'APP@1780656431.e2zPs6.supply-chain-vulnerability-connector'
export const SECURITY_POSTURE_ENTITY_IDS = [SIGNAL_SOURCES, VULNERABILITY_CONNECTOR, BACKEND] as const

const CONNECTION_IDS = [
  'APP@1780783993.JqIBPJ---APP@1777293133.OYEmP1@@archimate-serving',
  'APP@1780783993.JqIBPJ---APP@1780656431.e2zPs6@@archimate-serving',
] as const

const SCORES = new Map<string, number>([
  [SIGNAL_SOURCES, 0],
  [VULNERABILITY_CONNECTOR, 5.4],
  [BACKEND, 9.1],
])

interface ExecutionEntity {
  id: string
  column_values: Record<string, number> | null
}

interface ExecutionConnection {
  id: string
  source: string
  target: string
}

interface ExecutionResponse {
  entity_ids: string[]
  connection_ids: string[]
  entities: ExecutionEntity[]
  connections: ExecutionConnection[]
  total_entity_count: number
  returned_entity_count: number
  total_connection_count: number
  returned_connection_count: number
  query_summary: string
}

interface ProjectionItem {
  item_id: string
  item_kind: 'entity' | 'connection'
  style: Record<string, unknown>
}

interface ProjectionResponse {
  items: ProjectionItem[]
  rule_outcomes: {
    rule_index: number
    capability: string
    kind: string
    matched_count: number
    applied_count: number
    detail: null
  }[]
}

interface DiagramResponse {
  svg: string
  signal_banner: {
    classification: string
    available: boolean
    note: null
    basis_snapshots: { anchor_entity_id: string; snapshot_id: string; activated_at: string }[]
    generated_at: string
  }
}

const postureSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="980" height="480" viewBox="0 0 980 480" role="img" aria-labelledby="title description">
  <title id="title">Security posture by maximum CVSS score</title>
  <desc id="description">Synthetic documentation fixture showing three real application components colored from zero to ten.</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/>
    </marker>
  </defs>
  <g id="security-posture-graph">
  <rect width="980" height="480" rx="18" fill="#f8fafc"/>
  <text x="490" y="38" text-anchor="middle" font-family="sans-serif" font-size="22" font-weight="700" fill="#0f172a">Maximum open-finding CVSS by component</text>
  <text x="490" y="64" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#475569">Capture-only finding fixture · real repository entities and relationships</text>
  <path d="M 326 238 C 365 238, 368 148, 410 148" fill="none" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M 326 238 C 365 238, 368 350, 410 350" fill="none" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>
  <g data-entity-id="${SIGNAL_SOURCES}">
    <rect x="42" y="155" width="284" height="166" rx="14" fill="#fff7d6" stroke="#fbbf24" stroke-width="6"/>
    <text x="184" y="190" text-anchor="middle" font-family="sans-serif" font-size="13" font-weight="700" fill="#713f12">APPLICATION COMPONENT</text>
    <text x="184" y="227" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700" fill="#0f172a">Supply-Chain</text>
    <text x="184" y="253" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="700" fill="#0f172a">Signal Sources</text>
    <text x="184" y="292" text-anchor="middle" font-family="sans-serif" font-size="17" font-weight="700" fill="#92400e">0.0 CVSS · no open findings</text>
  </g>
  <g data-entity-id="${VULNERABILITY_CONNECTOR}">
    <rect x="410" y="82" width="520" height="132" rx="14" fill="#fff1dc" stroke="#ed701f" stroke-width="7"/>
    <text x="438" y="116" font-family="sans-serif" font-size="13" font-weight="700" fill="#7c2d12">APPLICATION COMPONENT</text>
    <text x="438" y="151" font-family="sans-serif" font-size="21" font-weight="700" fill="#0f172a">Supply-Chain &amp; Vulnerability Connector</text>
    <text x="438" y="188" font-family="sans-serif" font-size="18" font-weight="700" fill="#9a3412">5.4 CVSS · medium synthetic finding</text>
  </g>
  <g data-entity-id="${BACKEND}">
    <rect x="410" y="280" width="520" height="140" rx="14" fill="#fee2e2" stroke="#df3725" stroke-width="8"/>
    <text x="438" y="316" font-family="sans-serif" font-size="13" font-weight="700" fill="#7f1d1d">APPLICATION COMPONENT</text>
    <text x="438" y="354" font-family="sans-serif" font-size="23" font-weight="700" fill="#0f172a">Architecture Backend</text>
    <text x="438" y="395" font-family="sans-serif" font-size="19" font-weight="700" fill="#991b1b">9.1 CVSS · critical synthetic finding</text>
  </g>
  </g>
</svg>`

async function narrowExecution(route: Route): Promise<void> {
  const response = await route.fetch()
  const body = await response.json() as ExecutionResponse
  const entityIds = new Set<string>(SECURITY_POSTURE_ENTITY_IDS)
  body.entities = body.entities.filter((entity) => entityIds.has(entity.id))
    .map((entity) => ({ ...entity, column_values: { 'derived.max_cvss': SCORES.get(entity.id) ?? 0 } }))
  body.connections = body.connections.filter((connection) => CONNECTION_IDS.includes(
    connection.id as typeof CONNECTION_IDS[number]))
  body.entity_ids = [...SECURITY_POSTURE_ENTITY_IDS]
  body.connection_ids = [...CONNECTION_IDS]
  body.total_entity_count = body.returned_entity_count = body.entities.length
  body.total_connection_count = body.returned_connection_count = body.connections.length
  body.query_summary = 'Synthetic finding fixture: maximum open-finding CVSS for three real application components.'
  await route.fulfill({ response, json: body })
}

async function narrowProjection(route: Route): Promise<void> {
  const response = await route.fetch()
  const body = await response.json() as ProjectionResponse
  const retainedIds = new Set<string>([...SECURITY_POSTURE_ENTITY_IDS, ...CONNECTION_IDS])
  body.items = body.items.filter((item) => retainedIds.has(item.item_id))
  for (const item of body.items) {
    const score = SCORES.get(item.item_id)
    if (item.item_kind === 'entity' && score !== undefined) {
      item.style = { ...item.style, node_color: { position: score / 10, tokens: ['heat-low', 'heat-high'] } }
    }
  }
  body.rule_outcomes = [{
    rule_index: 0, capability: 'node_color', kind: 'applied', matched_count: 3, applied_count: 3, detail: null,
  }]
  await route.fulfill({ response, json: body })
}

async function narrowDiagram(route: Route): Promise<void> {
  const response = await route.fetch()
  const body = await response.json() as DiagramResponse
  body.svg = postureSvg
  body.signal_banner = {
    classification: 'TLP:WHITE', available: true, note: null,
    basis_snapshots: [{
      anchor_entity_id: BACKEND, snapshot_id: 'SYNTHETIC-DOCS-001', activated_at: '2026-07-22T00:00:00Z',
    }],
    generated_at: '2026-07-22T00:00:00Z',
  }
  await route.fulfill({ response, json: body })
}

export async function installSecurityPostureFixture(page: Page): Promise<void> {
  await addSyntheticBanner(page)
  await page.route('**/api/viewpoints/execute', narrowExecution)
  await page.route('**/api/viewpoints/execute-projection', narrowProjection)
  await page.route('**/api/viewpoints/execute-diagram', narrowDiagram)
}

export async function assertSecurityPostureFixture(page: Page): Promise<void> {
  await expect(page.locator('.signal-banner')).toContainText('TLP:WHITE', { timeout: 30_000 })
  await expect(page.getByTestId('synthetic-documentation-banner')).toBeVisible()
  await expect(page.locator('.vp-scale-gradient')).not.toHaveCount(0)
  await expect(page.locator('.svg-wrap')).toContainText('9.1 CVSS')
  await expect(page.locator('.svg-wrap')).toContainText('Supply-Chain & Vulnerability Connector')
}
