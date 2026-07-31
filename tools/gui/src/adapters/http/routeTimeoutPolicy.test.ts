import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PROXY_TIMEOUT_MS,
  LEGACY_TEMPLATES_BY_TIMEOUT_CLASS,
  PROXY_HEADROOM_MS,
  TEMPLATES_BY_TIMEOUT_CLASS,
  TIMEOUT_BUDGET_MS,
  proxyContextsFor,
  proxyTimeoutMs,
  timeoutBudgetForPath,
  timeoutClassForPath,
} from './routeTimeoutPolicy'

describe('timeoutClassForPath', () => {
  it('classifies the event stream as streaming, which never aborts', () => {
    expect(timeoutClassForPath('/api/events')).toBe('streaming')
    expect(timeoutBudgetForPath('/api/events')).toBeNull()
  })

  it('classifies derived-graph routes above the generic budget', () => {
    expect(timeoutClassForPath('/api/viewpoints/execute')).toBe('derived-graph')
    const budget = timeoutBudgetForPath('/api/viewpoints/execute')
    expect(budget).toBe(TIMEOUT_BUDGET_MS['derived-graph'])
    expect(budget).toBeGreaterThan(TIMEOUT_BUDGET_MS.default ?? 0)
  })

  it('gives an entity neighbourhood read the derived-graph budget its proxy already had', () => {
    // The disagreement this classification removes: the dev proxy allowed 65s while the client
    // aborted at 10s, so the shorter, unintended bound was the one users experienced. Identity in
    // mid-path is also why the patterns are templates: no prefix separates this from an entity read.
    expect(timeoutClassForPath('/api/entities/APP@1.ab.thing/neighbors')).toBe('derived-graph')
  })

  it('keeps every not-yet-renamed route in its class until the rename lands', () => {
    // Driven from the legacy list rather than naming one route: the list shrinks slice by slice,
    // and a hard-coded example would fail the moment its own rename landed — reporting a
    // regression where there was a completed migration. Empty is the end state, not a gap.
    for (const template of LEGACY_TEMPLATES_BY_TIMEOUT_CLASS['derived-graph']) {
      const concrete = template.replace(/\{[^}]+\}/g, 'PLACEHOLDER')
      expect(timeoutClassForPath(concrete)).toBe('derived-graph')
    }
  })

  it('falls back to the generic budget for an ordinary read', () => {
    expect(timeoutClassForPath('/api/entities')).toBe('default')
    expect(timeoutBudgetForPath('/api/entities')).toBe(TIMEOUT_BUDGET_MS.default)
  })

  it('does not let one template swallow a longer sibling segment', () => {
    expect(timeoutClassForPath('/api/diagrams')).toBe('derived-graph')
    expect(timeoutClassForPath('/api/diagram-refs')).toBe('default')
  })

  it('matches a path that carries a query string', () => {
    // A dev proxy matches against the request URL, query included; an end-anchored pattern would
    // fail on every request that has one.
    expect(timeoutClassForPath('/api/viewpoints/execute?trace=1')).toBe('derived-graph')
  })
})

describe('proxy budgets', () => {
  it('always exceeds the client budget, so the client aborts first', () => {
    expect(proxyTimeoutMs('derived-graph')).toBe(
      (TIMEOUT_BUDGET_MS['derived-graph'] ?? 0) + PROXY_HEADROOM_MS,
    )
    expect(DEFAULT_PROXY_TIMEOUT_MS).toBeGreaterThan(TIMEOUT_BUDGET_MS.default ?? 0)
  })

  it('leaves a streaming context with no budget at all', () => {
    expect(proxyTimeoutMs('streaming')).toBeUndefined()
  })

  it('offers a longer template before the shorter one it extends', () => {
    // Vite uses the first key that matches, so a specific rule listed after a broader one never
    // fires. The ordering is computed with the manifest; this asserts the document carries it.
    const contexts = proxyContextsFor('derived-graph')
    const svg = contexts.findIndex((pattern) => pattern.includes('/svg'))
    const detail = contexts.findIndex((pattern) => pattern.endsWith('/api/diagrams/[^/?#]+(\\?|$)'))
    expect(svg).toBeGreaterThanOrEqual(0)
    expect(detail).toBeGreaterThanOrEqual(0)
    expect(svg).toBeLessThan(detail)
  })

  it('emits one context per declared template, canonical and legacy alike', () => {
    expect(proxyContextsFor('derived-graph')).toHaveLength(
      TEMPLATES_BY_TIMEOUT_CLASS['derived-graph'].length +
        LEGACY_TEMPLATES_BY_TIMEOUT_CLASS['derived-graph'].length,
    )
  })
})
