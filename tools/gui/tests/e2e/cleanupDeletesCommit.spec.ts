import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'

/**
 * A cleanup delete in this suite says `dry_run=false`, because omitting it plans.
 *
 * Every write operation on the REST surface now defaults `dry_run` to `true` — plan unless told
 * otherwise. Four routes used to default to committing, and the specs that created viewpoint
 * definitions relied on that: their `afterEach` cleanup issued a bare
 * `request.delete('/api/viewpoints/…')` and got a deletion. The moment the default was made uniform,
 * those deletes became plans, and one full run leaked **247 lines** of definitions into the
 * engagement repository's `viewpoints.yaml`.
 *
 * It surfaced as an unrelated-looking assertion three spec files away — "every catalog definition
 * shows a non-blank criteria tree" found a leaked scope-only draft — which is the shape of every
 * cleanup leak: the damage is reported by whoever reads the catalogue next.
 *
 * So this is a source scan, in the suite that owns those specs. A behavioural test cannot see it: the
 * bare delete answers 200 and reports the plan it made, which is a success by every measure except
 * the one that matters. What is being forbidden is a spelling, and the guard belongs beside the
 * spelling.
 */

const E2E_DIR = import.meta.dirname

/** A `.delete(` call naming an `/api/…` path. */
const API_DELETE = /\.delete\(\s*[`'"][^`'"]*\/api\/[^`'"]*[`'"]/

/**
 * Routes that take no `dry_run` at all, so there is nothing to say. The assurance write surface
 * gates on the confidential store's own unlock and capability checks rather than on a plan flag.
 */
const NO_DRY_RUN_SURFACES = ['/api/assurance/']

const specSources = (): readonly { name: string; text: string }[] =>
  readdirSync(E2E_DIR)
    .filter((entry) => entry.endsWith('.spec.ts'))
    .map((entry) => ({ name: entry, text: readFileSync(join(E2E_DIR, entry), 'utf8') }))

test.describe('cleanup deletes', () => {
  test('the scan reads the specs it means to check', () => {
    const names = specSources().map((source) => source.name)
    expect(names.length).toBeGreaterThan(20)
    expect(names).toContain('viewpoint-editor.spec.ts')
  })

  test('every delete of an /api/ path commits rather than planning', () => {
    const offenders = specSources().flatMap(({ name, text }) =>
      text
        .split('\n')
        .map((line, index) => ({ line, at: `${name}:${index + 1}` }))
        .filter(({ line }) => API_DELETE.test(line))
        .filter(({ line }) => !NO_DRY_RUN_SURFACES.some((surface) => line.includes(surface)))
        .filter(({ line }) => !line.includes('dry_run=false'))
        // Prose that quotes the forbidden spelling is not the forbidden spelling. This file's own
        // docstring was the first thing the scan reported, which is a fair warning about scanning
        // source: the pattern has to exclude the places we write *about* code.
        .filter(({ line }) => !/^\s*(\/\/|\*|\/\*)/.test(line))
        .map(({ at, line }) => `${at}: ${line.trim()}`),
    )
    expect(
      offenders,
      'these delete an /api/ resource without `dry_run=false`, so they plan instead of deleting and '
        + 'leak whatever the spec created into the repository. Say what you mean, as the GUI adapter '
        + 'and the six sibling deletes already do.',
    ).toEqual([])
  })
})
