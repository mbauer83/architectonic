// @vitest-environment jsdom
/**
 * Stressors typed in quick succession: every line kept is written, in the order it was kept, or
 * visibly refused. The regression: a line kept while the line before it was still being written was
 * dropped without a word — two of six went missing — because the input declined Enter while the
 * analysis was saving.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick, type App } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../../application/ModelService'
import { NetworkError } from '../../../domain'
import { modelServiceKey } from '../../keys'
import { useStressAnalysis } from '../useStressAnalysis'
import StressorInput from '../../components/stressWorkspace/StressorInput.vue'

/** A write the test answers when it chooses, so a second write can be asked for while the first runs. */
interface Pending { readonly text: string; readonly answer: () => void; readonly refuse: () => void }

const fakeService = () => {
  const pending: Pending[] = []
  const written: string[] = []
  let inFlight = 0
  let overlapped = false
  const svc = {
    getDocument: () => Effect.succeed({ extra: {} }),
    readDocumentTables: () => Effect.succeed({ tables: {} }),
    readAnalysisIncidence: () => Effect.succeed(null),
    readAnalysisProgress: () => Effect.succeed(null),
    readTestSet: () => Effect.succeed(null),
    compareCandidate: () => Effect.succeed(null),
    listStressPerspectives: () => Effect.succeed({ frameworks: [] }),
    editDocumentTable: (_id: string, _table: string, rows: readonly { cells: Record<string, string> }[]) =>
      Effect.async<{ added_row_ids: string[] }, NetworkError>((resume) => {
        const text = rows[0].cells.stressor
        inFlight += 1
        if (inFlight > 1) overlapped = true
        pending.push({
          text,
          answer: () => {
            inFlight -= 1
            written.push(text)
            resume(Effect.succeed({ added_row_ids: [`S${written.length}`] }))
          },
          refuse: () => {
            inFlight -= 1
            resume(Effect.fail(new NetworkError({ status: 400, message: `refused: ${text}` })))
          },
        })
      }),
  }
  return { svc: svc as unknown as ModelService, pending, written, overlapped: () => overlapped }
}

/** Let every promise the composable is waiting on settle. */
const settle = async () => {
  for (let turn = 0; turn < 10; turn++) await new Promise((resolve) => setTimeout(resolve, 0))
}

/** Answer each write as it arrives, refusing the ones named, until none is left. */
const drain = async (pending: Pending[], refused: ReadonlySet<string> = new Set()) => {
  await settle()
  while (pending.length) {
    const next = pending.shift()!
    if (refused.has(next.text)) next.refuse()
    else next.answer()
    await settle()
  }
}

const add = (analysis: ReturnType<typeof useStressAnalysis>, stressor: string) =>
  analysis.edit('stressors', [{ op: 'add', cells: { stressor } }])

const LINES = ['one', 'two', 'three', 'four', 'five', 'six']

describe('writes asked for while one is running', () => {
  it('are all written, in the order asked, one at a time', async () => {
    const { svc, pending, written, overlapped } = fakeService()
    const analysis = useStressAnalysis(svc, () => 'DOC@1.a')

    const answers = LINES.map((line) => add(analysis, line))
    expect(analysis.saving.value).toBe(true)
    await drain(pending)

    expect(written).toEqual(LINES)
    expect(overlapped()).toBe(false)
    expect(await Promise.all(answers)).toEqual(LINES.map((_line, at) => [`S${at + 1}`]))
    expect(analysis.saving.value).toBe(false)
  })

  it('say a refusal, and keep saying it while the writes after it succeed', async () => {
    const { svc, pending, written } = fakeService()
    const analysis = useStressAnalysis(svc, () => 'DOC@1.a')

    const answers = LINES.map((line) => add(analysis, line))
    await drain(pending, new Set(['three']))

    expect(written).toEqual(['one', 'two', 'four', 'five', 'six'])
    expect((await Promise.all(answers))[2]).toBeNull()
    expect(analysis.error.value).toContain('refused: three')
  })
})

describe('the stressor line', () => {
  let app: App | null = null
  afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren() })

  it('hands on every line kept, even while the analysis is saving', async () => {
    const { svc, pending, written } = fakeService()
    const analysis = useStressAnalysis(svc, () => 'DOC@1.a')
    const host = document.createElement('div')
    document.body.append(host)
    app = createApp({
      render: () => h(StressorInput, {
        unwritten: [], placeholder: 'Write a stressor and press Enter',
        onWrite: (text: string) => { void add(analysis, text) },
      }),
    })
    app.provide(modelServiceKey, svc)
    app.mount(host)
    const input = host.querySelector<HTMLInputElement>('[data-testid="stressor-input"]')!

    for (const line of LINES) {
      input.value = line
      input.dispatchEvent(new Event('input'))
      await nextTick()
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      await nextTick()
      expect(input.value).toBe('')
    }
    expect(analysis.saving.value).toBe(true)
    await drain(pending)

    expect(written).toEqual(LINES)
  })
})
