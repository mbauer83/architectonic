import { Cause, Effect, Exit } from 'effect'
import { beforeAll, describe, expect, it } from 'vitest'
import { baseUrl } from './environment'
import { conformanceRepository } from './seed'
import { ADMIN_WRITE_STEPS, WRITE_STEPS, type WriteContext, type WriteStep } from './writeSteps'
import type { ModelRepository } from '../../src/ports/ModelRepository'

/**
 * The real client writing to the real server, for every write the client performs.
 *
 * `reads.conformance.test.ts` proves the decoders match the server for the 66 reads. This is the other
 * half, and it was 42 methods dark: every mutating port method plus the admin tier, registered in
 * `readCoverage.conformance.test.ts` as unexercised because the only backend available was serving the
 * dogfood repository. Nothing had ever driven `createEntity` through the adapter that ships.
 *
 * **Needs a fixture origin, and refuses to guess.** Every step authors or destroys, so this run must not
 * be pointed at a repository anybody keeps. It is driven by `tools/quality/gui_write_walk.py`, which
 * builds a disposable workspace, serves it on its own port, and passes the port in
 * `ARCH_GUI_WRITE_FIXTURE` along with the ids the fixture published. Without that variable this suite
 * fails rather than skipping: a write conformance suite that passed against no server would be quoted as
 * evidence, and one that silently ran against `:8000` would be worse.
 *
 * **Ordered, and it stops at the first failure.** The steps thread ids, so a failure early on makes
 * every later step fail for a reason that is not its own — twenty failures describing one. So the run
 * reports the first failure with its cause and marks the rest unrun, which is what a stateful walk can
 * honestly say.
 */

/** What the orchestrator publishes about the fixture it built. Absent means: do not run. */
interface FixtureHandoff {
  readonly fixtureEntity: string
  readonly fixtureOtherEntity: string
  readonly doomedEntity: string
  readonly fixtureDiagram: string
  readonly annotated: { diagram: string, classifier: string, attribute: string }
  readonly adminMode: boolean
}

const handoff = (): FixtureHandoff | null => {
  const raw = process.env.ARCH_GUI_WRITE_FIXTURE
  if (raw === undefined || raw === '') return null
  return JSON.parse(raw) as FixtureHandoff
}

const failureText = (exit: Exit.Exit<unknown, unknown>): string =>
  Exit.isSuccess(exit) ? '' : Cause.pretty(exit.cause)

const label = (step: WriteStep): string =>
  step.variant === undefined ? String(step.method) : `${String(step.method)} (${step.variant})`

/** A refusal that rode inside a success: 200 with `wrote: false` and the reason attached. */
const refusal = (answer: unknown): string | null => {
  const payload = answer as { wrote?: unknown, verification?: { issues?: unknown } } | null
  if (payload?.wrote !== false) return null
  return `wrote: false — ${JSON.stringify(payload.verification?.issues ?? payload)?.slice(0, 400)}`
}

describe('write conformance against a fixture backend', () => {
  const fixture = handoff()
  let repo: ModelRepository
  const outcomes = new Map<string, string>()

  beforeAll(async () => {
    expect(
      fixture,
      'ARCH_GUI_WRITE_FIXTURE is unset. This suite writes and deletes, so it runs only against the '
        + 'disposable workspace its orchestrator builds:\n'
        + '  uv run tools/quality/gui_write_walk.py\n'
        + 'It refuses rather than skipping, because a write conformance run that passed against no '
        + 'server — or against yours — is worse than one that is absent.',
    ).not.toBeNull()
    if (fixture === null) return

    repo = conformanceRepository()
    const context: WriteContext = {
      fixtureEntity: fixture.fixtureEntity,
      fixtureOtherEntity: fixture.fixtureOtherEntity,
      doomedEntity: fixture.doomedEntity,
      fixtureDiagram: fixture.fixtureDiagram,
      annotated: fixture.annotated,
      created: {},
      groupSlug: 'gui-walk-project',
    }

    // Which tier this run walks is the orchestrator's decision, not this file's: `--admin-mode` is
    // process-wide, so the backend it started can serve one of the two and never both.
    const steps = fixture.adminMode ? ADMIN_WRITE_STEPS : WRITE_STEPS
    let stopped = false
    for (const step of steps) {
      if (stopped) {
        outcomes.set(label(step), 'not run: an earlier step failed')
        continue
      }
      const exit = await Effect.runPromiseExit(
        Effect.suspend(() => step.run(repo, context)),
      )
      if (Exit.isFailure(exit)) {
        outcomes.set(label(step), failureText(exit))
        stopped = true
        continue
      }
      const refused = step.mutates === false ? null : refusal(exit.value)
      if (refused !== null) {
        outcomes.set(label(step), refused)
        stopped = true
        continue
      }
      step.captures?.(exit.value, context)
      outcomes.set(label(step), '')
    }
  }, 300_000)

  it('reaches the origin its orchestrator built', () => {
    expect(fixture).not.toBeNull()
    expect(baseUrl()).not.toContain(':8000')
  })

  const steps = handoff()?.adminMode === true ? ADMIN_WRITE_STEPS : WRITE_STEPS
  for (const step of steps) {
    it(`${label(step)} writes and answers decodably`, () => {
      const outcome = outcomes.get(label(step))
      expect(outcome, `${label(step)} did not run at all`).toBeDefined()
      // Checked for a *refusal* as well as an error, because these routes answer 200 with
      // `wrote: false` when they decline — the trap this whole release keeps finding.
      expect(outcome, `${label(step)}\n${outcome ?? ''}`).toBe('')
    })
  }
})
