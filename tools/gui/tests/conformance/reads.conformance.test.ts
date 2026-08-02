import { Effect, Exit, Cause } from 'effect'
import { beforeAll, describe, expect, it } from 'vitest'
import { baseUrl } from './environment'
import { conformanceRepository, discoverSeed, type ConformanceSeed } from './seed'
import { READ_STEPS, stepLabel, type ReadStep } from './readSteps'
import type { ModelRepository } from '../../src/ports/ModelRepository'

/**
 * The real client decoding the real server, for every read the client performs.
 *
 * `contracts:check` proves the hand-written decoders match the published *document*. This proves
 * they match the *server*, and neither implies the other — which is the whole finding of handoff
 * §1.2. A JSON-Schema walk over the same 66 GET operations reported zero divergences against a
 * reintroduced FMEA defect that made the entire matrix render blank, because FastAPI publishes a
 * defaulted field as not-required while the generated TypeScript and the client's decoder both
 * treat it as always sent. Three of the four artefacts derived from one document agreed the field
 * was required; the only one that disagreed is the one a schema walk consults.
 *
 * What caught that defect was the client's decoder running over the server's bytes. That is this.
 *
 * Needs a backend: `E2E_BASE_URL` (default `http://localhost:8000`). It refuses to run rather than
 * skipping when there is none — a conformance suite that passes with no server is worse than
 * absent, because it is quoted as evidence.
 */

const reachable = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${baseUrl()}/api/stats`)
    return response.ok
  } catch {
    return false
  }
}

const failureText = (exit: Exit.Exit<unknown, unknown>): string => {
  if (Exit.isSuccess(exit)) return ''
  return Cause.pretty(exit.cause)
}

describe('decoder conformance against a live backend', () => {
  let repo: ModelRepository
  let seed: ConformanceSeed

  beforeAll(async () => {
    expect(
      await reachable(),
      `no backend at ${baseUrl()} — start one (\`arch-backend\`) or set E2E_BASE_URL`,
    ).toBe(true)
    repo = conformanceRepository()
    seed = await discoverSeed(repo)
  }, 120_000)

  it('discovers every seed the detail reads need', () => {
    const absent = Object.entries(seed)
      .filter(([, value]) => value === null)
      .map(([key]) => key)
    // Not an assertion that the dogfood repository is complete — it is a report, so a seed that
    // silently stopped being discoverable shows up here rather than as a wave of skips nobody reads.
    expect(absent, `seeds absent, so the steps needing them will skip: ${absent.join(', ')}`).toEqual(
      [],
    )
  })

  for (const step of READ_STEPS) {
    it(`${stepLabel(step)} decodes what the server sends`, async () => {
      const missing = (step.needs ?? []).filter((key) => seed[key] === null)
      if (missing.length > 0) {
        // A seed the fixture cannot supply is a fixture gap, and naming it is the useful outcome.
        expect.fail(`seed absent: ${missing.join(', ')}`)
      }
      const exit = await Effect.runPromiseExit(runStep(step, repo, seed))
      expect(Exit.isSuccess(exit), `${stepLabel(step)}: ${failureText(exit)}`).toBe(true)
    }, 120_000)
  }
})

const runStep = (
  step: ReadStep,
  repo: ModelRepository,
  seed: ConformanceSeed,
): Effect.Effect<unknown, unknown> =>
  Effect.suspend(() => step.run(repo, seed))
