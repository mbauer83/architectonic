import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { Effect } from 'effect'
import type { DiagramSummary, ViewpointDefinitionEnvelope } from '../../domain'
import type { LayoutGeometry } from '../../domain/schemas/diagramLayoutGeometry'
import type { ViewpointExecutionResult } from '../../domain/schemas/viewpoints'
import { type ScopeAccess, useAnalysisScope } from './useAnalysisScope'

const GENERATED = { artifact_id: '', name: 'generated' } as unknown as LayoutGeometry
const STORED = { artifact_id: 'ARC@1.Stored', name: 'stored' } as unknown as LayoutGeometry
const POPULATION = { entity_ids: ['APP@1.Aaaaaa', 'APP@2.Bbbbbb'] } as unknown as ViewpointExecutionResult
const DIAGRAMS = [{ artifact_id: 'ARC@1.Stored', name: 'Stored diagram' }] as unknown as DiagramSummary[]
const VIEWPOINTS = [
  { slug: 'applied', name: 'Applied viewpoint' }, { slug: 'unapplied', name: 'Unapplied viewpoint' },
] as unknown as ViewpointDefinitionEnvelope[]

/** The access the scope reads through; *calls* records what it asked. */
const fakeAccess = () => {
  const calls: string[] = []
  const access = {
    getDiagramContext: () => Effect.succeed({ entities: [] }),
    readLayoutGeometry: (id: string) => {
      calls.push(`stored ${id}`)
      return Effect.succeed(STORED)
    },
    drawScope: (scope: readonly string[], name: string) => {
      calls.push(`generated ${scope.join(' ')} as ${name}`)
      return Effect.succeed(GENERATED)
    },
    executeViewpoint: () => Effect.succeed(POPULATION),
    getViewpointReferencers: (slug: string) => Effect.succeed(
      slug === 'applied' ? [{ artifact_id: 'ARC@1.Stored', target_kind: 'diagram' as const }] : [],
    ),
    search: () => Effect.succeed({ hits: [] }),
  } as unknown as ScopeAccess
  return { access, calls }
}

const settle = async () => {
  await vi.runAllTimersAsync()
  await nextTick()
}

describe('the scope of the architecture under evaluation (Q36)', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('draws a viewpoint on a stored diagram that applies it', async () => {
    const { access, calls } = fakeAccess()
    const scope = useAnalysisScope(access, { diagrams: () => DIAGRAMS, viewpoints: () => VIEWPOINTS })
    scope.choose.source('viewpoint')
    await scope.runViewpoint('applied')
    await settle()

    expect(scope.drawnOn.value).toBe('ARC@1.Stored')
    expect(scope.drawing.value).toBe(STORED)
    expect(scope.subject.value).toBe('Applied viewpoint')
    expect(calls).toEqual(['stored ARC@1.Stored'])
  })

  it('draws a viewpoint no stored diagram applies as a view generated from its population', async () => {
    const { access, calls } = fakeAccess()
    const scope = useAnalysisScope(access, { diagrams: () => DIAGRAMS, viewpoints: () => VIEWPOINTS })
    scope.choose.source('viewpoint')
    await scope.runViewpoint('unapplied')
    await settle()

    expect(scope.drawnOn.value).toBe('')
    expect(scope.drawing.value).toBe(GENERATED)
    expect(calls).toEqual(['generated APP@1.Aaaaaa APP@2.Bbbbbb as Unapplied viewpoint'])
  })

  it('draws the elements ticked in a search as a generated view, once the ticks settle', async () => {
    const { access, calls } = fakeAccess()
    const scope = useAnalysisScope(access, { diagrams: () => DIAGRAMS, viewpoints: () => VIEWPOINTS })
    scope.choose.source('search')
    scope.tick('APP@1.Aaaaaa')
    await nextTick()
    scope.tick('APP@2.Bbbbbb')
    await settle()

    expect(scope.ids.value).toEqual(['APP@1.Aaaaaa', 'APP@2.Bbbbbb'])
    expect(scope.drawing.value).toBe(GENERATED)
    expect(calls).toEqual(['generated APP@1.Aaaaaa APP@2.Bbbbbb as The scope'])
  })
})
