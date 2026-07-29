import { describe, it, expect } from 'vitest'
import {
  MODELABLE_ARCH_TYPES,
  isUnboundControlNode,
  domainForArchType,
  emptyModelThisForm,
  modelThisBody,
  parseBindOutcome,
} from '../ModelThisPanel.helpers'

describe('isUnboundControlNode', () => {
  it('is true only for an unbound-pending control-structure node', () => {
    expect(isUnboundControlNode('control-structure-node', 'unbound-pending')).toBe(true)
  })

  it('is false for bound or non-control nodes', () => {
    expect(isUnboundControlNode('control-structure-node', 'bound')).toBe(false)
    expect(isUnboundControlNode('hazard', 'unbound-pending')).toBe(false)
    expect(isUnboundControlNode(undefined, undefined)).toBe(false)
  })
})

describe('domainForArchType', () => {
  it('maps technology types to the technology layer', () => {
    expect(domainForArchType('node')).toBe('technology')
    expect(domainForArchType('system-software')).toBe('technology')
  })

  it('defaults to the application layer', () => {
    expect(domainForArchType('application-component')).toBe('application')
    expect(domainForArchType('grouping')).toBe('application')
  })
})

describe('modelThisBody', () => {
  it('builds the request with a derived domain and trimmed name', () => {
    const form = { ...emptyModelThisForm('  Brake controller '), archType: 'node', separationOfDuties: true }
    expect(modelThisBody('CSN@1', form)).toEqual({
      assurance_node_id: 'CSN@1',
      suggested_arch_type: 'node',
      suggested_name: 'Brake controller',
      domain: 'technology',
      separation_of_duties: true,
    })
  })

  it('defaults the form to an application component', () => {
    expect(emptyModelThisForm('x').archType).toBe('application-component')
    expect(MODELABLE_ARCH_TYPES).toContain('application-component')
  })
})

describe('parseBindOutcome', () => {
  it('maps a bound response', () => {
    const out = parseBindOutcome(200, { outcome: 'bound', arch_artifact_id: 'APP@9' })
    expect(out.kind).toBe('bound')
    expect(out.archId).toBe('APP@9')
  })

  it('maps a task-required response', () => {
    expect(parseBindOutcome(200, { outcome: 'task_required', task: 'x' }).kind).toBe('task')
  })

  it('maps locked, not-found, and invalid responses to errors', () => {
    expect(parseBindOutcome(423, {}).kind).toBe('error')
    expect(parseBindOutcome(404, {}).kind).toBe('error')
    expect(parseBindOutcome(409, { message: 'already bound' }).message).toBe('already bound')
  })
})
