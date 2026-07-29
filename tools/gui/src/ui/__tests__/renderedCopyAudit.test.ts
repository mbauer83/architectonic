import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

/**
 * Rendered-copy audit: user-facing copy says "Enterprise", never "Global".
 * Internal identifiers (is_global, scope=global, /global/* redirects, CSS class
 * names, GAR terminology, compatibility comments) keep their names — this scan
 * only inspects TEXT rendered by templates.
 */

const SRC = resolve(__dirname, '..')

/** GAR terminology keeps its name: the artifact type IS
 * global-artifact-reference, and renaming this copy would detach it from the
 * term users meet in raw reads and promotion output. */
const ALLOWLISTED_CHUNKS = [
  'other connections, diagrams, or global references still depend on the entity.',
]

const vueFiles = (dir: string): string[] => {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      out.push(...vueFiles(path))
    } else if (name.endsWith('.vue')) {
      out.push(path)
    }
  }
  return out
}

const templateOf = (source: string): string => {
  const start = source.indexOf('<template>')
  const end = source.lastIndexOf('</template>')
  return start === -1 || end === -1 ? '' : source.slice(start, end)
}

/** Rendered text between tags — attribute values (classes, internal params) excluded. */
const renderedTextChunks = (template: string): string[] => {
  const chunks: string[] = []
  const pattern = />([^<>{}]+)</g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(template)) !== null) {
    chunks.push(match[1])
  }
  return chunks
}

describe('rendered copy says Enterprise, never Global', () => {
  it('no template renders the word Global as user-facing text', () => {
    const offenders: string[] = []
    for (const file of vueFiles(SRC)) {
      const template = templateOf(readFileSync(file, 'utf8'))
      for (const chunk of renderedTextChunks(template)) {
        if (!/\bglobal\b/i.test(chunk)) continue
        if (ALLOWLISTED_CHUNKS.some((allowed) => chunk.includes(allowed))) continue
        offenders.push(`${file}: ${chunk.trim()}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('the key surfaces render Enterprise', () => {
    const expectations: Array<[string, string]> = [
      ['components/EntityDetailHeader.vue', 'Enterprise'],
      ['components/DiagramDetailHeader.vue', 'Promote to Enterprise'],
      ['views/DocumentDetailView.vue', 'Promote to Enterprise'],
      ['views/PromoteView.vue', 'Promote to Enterprise Repository'],
      ['views/HomeView.vue', 'Enterprise'],
    ]
    for (const [file, needle] of expectations) {
      const template = templateOf(readFileSync(join(SRC, file), 'utf8'))
      expect(template, file).toContain(needle)
    }
  })
})
