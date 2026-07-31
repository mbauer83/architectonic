#!/usr/bin/env node
/**
 * Generate or verify the committed OpenAPI-derived TypeScript.
 *
 *   node scripts/contracts.mjs check      # non-mutating: fails if the committed file is stale
 *   node scripts/contracts.mjs generate   # writes the committed file
 *
 * `check` is deliberately self-contained. It obtains the document **in-process** from the backend
 * application object, generates into a temporary directory, and compares — so it needs no running
 * server, and it writes nothing into the working tree. A pre-commit gate that required a server
 * started by a later gate could not run at the moment it exists to protect, and one that wrote
 * into the tree would make its own subject stale.
 */

import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'

const GUI_ROOT = resolve(import.meta.dirname, '..')
const REPO_ROOT = resolve(GUI_ROOT, '..', '..')
const COMMITTED = join(GUI_ROOT, 'src', 'domain', 'schemas', 'openapi.generated.ts')

const HEADER = `/**
 * Generated from the backend's OpenAPI document. Do not edit.
 *
 * Regenerate with \`npm run contracts:generate\`; \`npm run contracts:check\` fails when this file
 * and the backend disagree. This file is the *oracle* the hand-written effect schemas are verified
 * against — it is not a decoder, because it carries no runtime semantics.
 */
`

const run = (command, args, options = {}) =>
  execFileSync(command, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'], ...options })

/** The OpenAPI document, straight from the application object. */
const dumpDocument = (destination) => {
  run('uv', ['run', 'tools/openapi/dump_openapi.py', destination], { cwd: REPO_ROOT })
}

const generateTypes = (documentPath) => {
  const output = run(
    'npx',
    // No `--enum`: a TypeScript enum is nominal, so a generated enum member is not
    // type-equal to the string literal a hand-written decoder produces, and the type-level
    // contract assertions could never hold. String literal unions compare structurally.
    ['--no-install', 'openapi-typescript', documentPath, '--alphabetize'],
    { cwd: GUI_ROOT },
  )
  return HEADER + output
}

const withTempDirectory = (body) => {
  const directory = mkdtempSync(join(tmpdir(), 'arch-contracts-'))
  try {
    return body(directory)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
}

const firstDifferenceLine = (expected, actual) => {
  const a = expected.split('\n')
  const b = actual.split('\n')
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    if (a[i] !== b[i]) return { line: i + 1, committed: a[i] ?? '<end of file>', current: b[i] ?? '<end of file>' }
  }
  return null
}

const mode = process.argv[2]

if (mode !== 'check' && mode !== 'generate') {
  console.error('usage: contracts.mjs <check|generate>')
  process.exit(2)
}

withTempDirectory((directory) => {
  const documentPath = join(directory, 'openapi.json')
  dumpDocument(documentPath)
  const generated = generateTypes(documentPath)

  if (mode === 'generate') {
    mkdirSync(dirname(COMMITTED), { recursive: true })
    writeFileSync(COMMITTED, generated, 'utf8')
    console.log(`contracts: wrote ${COMMITTED}`)
    return
  }

  if (!existsSync(COMMITTED)) {
    console.error(
      `contracts: ${COMMITTED} does not exist.\n` +
        'Run `npm run contracts:generate` and commit the result.',
    )
    process.exit(1)
  }
  const committed = readFileSync(COMMITTED, 'utf8')
  if (committed === generated) {
    console.log('contracts: committed OpenAPI types match the backend')
    return
  }
  const difference = firstDifferenceLine(committed, generated)
  console.error(
    'contracts: the committed OpenAPI types are stale.\n' +
      (difference
        ? `  first difference at line ${difference.line}\n` +
          `    committed: ${difference.committed}\n` +
          `    current:   ${difference.current}\n`
        : '') +
      'Run `npm run contracts:generate` and commit the result.',
  )
  process.exit(1)
})
