import { describe, it, expect } from 'vitest'
import { Effect } from 'effect'
import type { ModelRepository } from '../ports/ModelRepository'
import { makeModelService } from './ModelService'

/**
 * Delegation contract for the typed list params: the service forwards the FULL
 * diagram params object (a positional-args version silently dropped `group` on
 * the way to the adapter) and the document params including `scope`.
 */

const capturingRepo = () => {
  const calls: Record<string, unknown[]> = {}
  const record =
    (name: string) =>
    (...args: unknown[]) => {
      calls[name] = args
      return Effect.succeed({ total: 0, items: [] })
    }
  const repo = {
    listDiagrams: record('listDiagrams'),
    listDocuments: record('listDocuments'),
  } as unknown as ModelRepository
  return { repo, calls }
}

describe('ModelService.listDiagrams', () => {
  it('forwards the whole params object — group and scope are not dropped', () => {
    const { repo, calls } = capturingRepo()
    const params = { diagram_type: 'archimate-motivation', status: 'draft', group: 'views', scope: 'global' }
    void makeModelService(repo).listDiagrams(params)
    expect(calls.listDiagrams).toEqual([params])
  })

  it('forwards an omitted params object as-is', () => {
    const { repo, calls } = capturingRepo()
    void makeModelService(repo).listDiagrams()
    expect(calls.listDiagrams).toEqual([undefined])
  })
})

describe('ModelService.listDocuments', () => {
  it('forwards scope alongside the existing filters', () => {
    const { repo, calls } = capturingRepo()
    const params = { doc_type: 'adr', group: 'decisions', scope: 'engagement' }
    void makeModelService(repo).listDocuments(params)
    expect(calls.listDocuments).toEqual([params])
  })
})
