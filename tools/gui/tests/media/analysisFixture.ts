import { expect, type APIRequestContext } from '@playwright/test'

/**
 * The data the candidate and stress-analysis figures are taken of, written through the product's own
 * API and deleted afterwards.
 *
 * Candidates and stress analyses are files of the engagement repository, so a figure of one needs one
 * to exist — and must not leave it behind. Every write here is matched by a delete in `removeAll`,
 * real rather than dry-run, children before what they stack on and the analysis document before its
 * naive candidate (a candidate is kept while anything names it). The figures name the self-model's
 * promotion pipeline, the worked example the guides walk through.
 */

export const DIAGRAM = 'ARC@1783185029.4Ayzz3.one-enterprise-repository-many-engagements'
export const PROMOTION_SERVICE = 'SRV@1712870400.Uv9Wx9'
export const INDEX_STORE = 'APP@1786967678.R_K3YAQ'
export const GIT_SYNC = 'APP@1777293134.tY3JIK'

interface Written { record: { id: string }; version: string }

/** What a figure created, in the order it must be deleted. */
export class AnalysisFixture {
  private readonly documents: string[] = []
  private readonly candidates: string[] = []

  constructor(readonly request: APIRequestContext) {}

  async candidate(record: Record<string, unknown>, operations: unknown[] = []): Promise<string> {
    const created = await this.request.post('/api/change-sets', { data: { record, operations } })
    expect(created.ok(), await created.text()).toBe(true)
    const id = ((await created.json()) as Written).record.id
    this.candidates.unshift(id)
    return id
  }

  async record(candidate: string, operations: unknown[]): Promise<void> {
    const read = await this.request.get(`/api/change-sets/${encodeURIComponent(candidate)}`)
    const { version } = (await read.json()) as Written
    const recorded = await this.request.post(`/api/change-sets/${encodeURIComponent(candidate)}/operations`,
      { data: { based_on: version, operations } })
    expect(recorded.ok(), await recorded.text()).toBe(true)
  }

  async startAnalysis(title: string, context: string, naive: Record<string, unknown>): Promise<{ document: string; naive: string }> {
    const started = await this.request.post('/api/stress-analyses', { data: { title, context, naive } })
    expect(started.ok(), await started.text()).toBe(true)
    const body = (await started.json()) as { document: string; naive_candidate: Written }
    this.documents.unshift(body.document)
    this.candidates.unshift(body.naive_candidate.record.id)
    return { document: body.document, naive: body.naive_candidate.record.id }
  }

  async table(document: string, table: string, rows: unknown[]): Promise<void> {
    const written = await this.request.patch(`/api/documents/${encodeURIComponent(document)}/tables/${table}`,
      { data: { rows, dry_run: false } })
    expect(written.ok(), await written.text()).toBe(true)
  }

  async removeAll(): Promise<void> {
    for (const id of this.documents.splice(0)) {
      const deleted = await this.request.delete(`/api/documents/${encodeURIComponent(id)}?dry_run=false`)
      expect(deleted.ok(), await deleted.text()).toBe(true)
    }
    for (const id of this.candidates.splice(0)) {
      const deleted = await this.request.delete(`/api/change-sets/${encodeURIComponent(id)}?dry_run=false`)
      expect(deleted.status(), await deleted.text()).toBe(204)
    }
  }
}

export const NAIVE_NAME = 'Promotion pipeline as it stands'
export const ADAPTATION_NAME = 'Queued promotions'

/**
 * The guide's worked example, as far as a figure needs it: the naive architecture sketched (three model
 * elements and a created Promotion Queue), six design stressors with what happens under each, their end
 * states and incidence, an adaptation stacked on the naive, and a test set judged on both.
 */
export async function promotionPipelineAnalysis(fixture: AnalysisFixture, { queue = true } = {}): Promise<{
  document: string; naive: string; adaptation: string
}> {
  const { document, naive } = await fixture.startAnalysis(
    'Stress analysis — promotion pipeline',
    'Engagements multiply over the next two years; the analysis informs whether promotion needs a queue.',
    { name: NAIVE_NAME, scope: [PROMOTION_SERVICE, INDEX_STORE, GIT_SYNC] },
  )
  if (queue) {
    await fixture.record(naive, [
      { op: 'create_entity', fields: { artifact_type: 'application-component', name: 'Promotion Queue', group: 'platform-core' } },
    ])
    const created = await createdId(fixture, naive, 'Promotion Queue')
    await fixture.record(naive, [
      { op: 'add_connection', source_entity: created, connection_type: 'archimate-serving', target_entity: PROMOTION_SERVICE },
    ])
  }

  await fixture.table(document, 'end-states', [
    { op: 'add', cells: { end_state: 'Promotions stall' } },
    { op: 'add', cells: { end_state: 'Promotion loses its reviewers' } },
  ])
  const design = [
    ['Forty engagements promote in the same week', 'economic', 'E1', 'Promotions wait behind one another for days.'],
    ['The enterprise repository host is unavailable for two days', 'technological', 'E1', 'No promotion can land; work piles up.'],
    ['The organisation merges with a company that uses another repository', 'key partners', '', ''],
    ['Promotion reviewers leave and are not replaced', 'key people', 'E2', 'Submitted promotions are never reviewed.'],
    ['A regulator requires every promotion to be signed off by a named person', 'legal', 'E2', ''],
    ['A second architecture team adopts its own modelling conventions', 'culture', '', ''],
  ] as const
  await fixture.table(document, 'stressors', design.map(([stressor, kind, endState, consequence]) => ({
    op: 'add',
    cells: { stressor, kind, set: 'design', ...(endState ? { end_state: endState } : {}), ...(consequence ? { consequence } : {}) },
  })))
  await fixture.table(document, 'incidence', [
    // Model elements only: a tick on an element the naive architecture creates is currently read as one
    // it no longer has, and the row would carry that warning.
    ['S1', PROMOTION_SERVICE], ['S1', INDEX_STORE],
    ['S2', GIT_SYNC], ['S2', PROMOTION_SERVICE],
    ['S4', PROMOTION_SERVICE], ['S5', PROMOTION_SERVICE],
  ].map(([stressor, component]) => ({ op: 'add', cells: { stressor, component } })))

  const adaptation = await fixture.candidate({ name: ADAPTATION_NAME, parent: naive }, [
    { op: 'create_entity', fields: { artifact_type: 'application-component', name: 'Promotion Retry Worker', group: 'platform-core' } },
  ])
  await fixture.table(document, 'adaptations', [
    { op: 'add', cells: { end_states: ['E1'], candidate_architecture: adaptation, integration: 'candidate' } },
  ])

  await fixture.table(document, 'stressors', [
    'Engagement repositories move to a new hosting provider',
    'Promotion volume halves after a reorganisation',
    'An audit asks who approved each promotion in the last year',
  ].map((stressor) => ({ op: 'add', cells: { stressor, set: 'test' } })))
  const verdicts: [string, string, string, string][] = [
    ['S7', 'naive', 'degrades', 'Promotions pause while the remotes are re-pointed.'],
    ['S8', 'naive', 'survives', 'Less load changes nothing.'],
    ['S9', 'naive', 'fails', 'Approvals are not recorded anywhere a reader can find.'],
    ['S7', adaptation, 'survives', 'The queue holds promotions until the new host answers.'],
    ['S8', adaptation, 'survives', 'The queue drains faster.'],
    ['S9', adaptation, 'degrades', 'The queue records who released each promotion, not who approved it.'],
  ]
  await fixture.table(document, 'survival', verdicts.map(([stressor, architecture, verdict, reasoning]) => ({
    op: 'add', cells: { stressor, architecture, verdict, reasoning },
  })))
  return { document, naive, adaptation }
}

async function createdId(fixture: AnalysisFixture, candidate: string, name: string): Promise<string> {
  const read = await fixture.request.get(`/api/change-sets/${encodeURIComponent(candidate)}`)
  const { record } = (await read.json()) as { record: { changes: { operations: { op: string; artifact_id?: string; fields?: { name?: string } }[] } } }
  const created = record.changes.operations.find((one) => one.op === 'create_entity' && one.fields?.name === name)
  expect(created?.artifact_id, `the candidate should create ${name}`).toBeTruthy()
  return created!.artifact_id!
}
