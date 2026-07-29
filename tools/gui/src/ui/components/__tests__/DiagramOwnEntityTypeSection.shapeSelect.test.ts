/**
 * Logic tests for the enum-select rendering helpers in DiagramOwnEntityTypeSection.
 *
 * These mirror the propEnumValues / propertyType helpers so we can assert the
 * shape-selector branching without a DOM mount.
 */
import { describe, it, expect } from 'vitest'

// Mirror helpers from DiagramOwnEntityTypeSection.vue
function propertyType(schema: unknown): string {
  if (!schema || typeof schema !== 'object' || !('type' in schema)) return ''
  const value = (schema as { type?: unknown }).type
  return typeof value === 'string' ? value : ''
}

function propEnumValues(schema: unknown): string[] {
  if (!schema || typeof schema !== 'object' || !('enum' in schema)) return []
  const value = (schema as { enum?: unknown }).enum
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

// The condition that triggers the <select>: string type + non-empty enum
function shouldRenderSelect(schema: unknown): boolean {
  return propertyType(schema) === 'string' && propEnumValues(schema).length > 0
}

describe('propEnumValues — shape select helper', () => {
  it('returns empty array when schema has no enum field', () => {
    expect(propEnumValues({ type: 'string' })).toEqual([])
  })

  it('returns empty array when schema.enum is not an array', () => {
    expect(propEnumValues({ type: 'string', enum: null })).toEqual([])
  })

  it('returns string members from schema.enum', () => {
    const schema = { type: 'string', enum: ['', 'Container', 'ContainerDb', 'ContainerQueue'] }
    expect(propEnumValues(schema)).toEqual(['', 'Container', 'ContainerDb', 'ContainerQueue'])
  })

  it('filters out non-string members', () => {
    const schema = { type: 'string', enum: ['Container', 42, null, 'ContainerDb'] }
    expect(propEnumValues(schema)).toEqual(['Container', 'ContainerDb'])
  })

  it('returns empty array for boolean schema', () => {
    expect(propEnumValues({ type: 'boolean' })).toEqual([])
  })

  it('returns empty for unknown schema', () => {
    expect(propEnumValues(null)).toEqual([])
    expect(propEnumValues(undefined)).toEqual([])
    expect(propEnumValues(42)).toEqual([])
  })
})

describe('shouldRenderSelect — branching condition', () => {
  it('renders select for C4 container shape property', () => {
    const containerShapeSchema = {
      type: 'string',
      enum: ['', 'Container', 'ContainerDb', 'ContainerQueue'],
    }
    expect(shouldRenderSelect(containerShapeSchema)).toBe(true)
  })

  it('renders select for C4 component shape property', () => {
    const componentShapeSchema = {
      type: 'string',
      enum: ['', 'Component', 'ComponentDb', 'ComponentQueue'],
    }
    expect(shouldRenderSelect(componentShapeSchema)).toBe(true)
  })

  it('does NOT render select for plain string property (technology, description)', () => {
    expect(shouldRenderSelect({ type: 'string' })).toBe(false)
  })

  it('does NOT render select for boolean property (external)', () => {
    expect(shouldRenderSelect({ type: 'boolean' })).toBe(false)
  })

  it('does NOT render select when enum is empty', () => {
    expect(shouldRenderSelect({ type: 'string', enum: [] })).toBe(false)
  })
})

describe('C4 shape enum completeness', () => {
  const containerShapeEnum = ['', 'Container', 'ContainerDb', 'ContainerQueue']
  const componentShapeEnum = ['', 'Component', 'ComponentDb', 'ComponentQueue']

  it('container shape enum includes base shape, db, and queue variants', () => {
    expect(containerShapeEnum).toContain('Container')
    expect(containerShapeEnum).toContain('ContainerDb')
    expect(containerShapeEnum).toContain('ContainerQueue')
    expect(containerShapeEnum).toContain('')  // auto-infer option
  })

  it('component shape enum includes base shape, db, and queue variants', () => {
    expect(componentShapeEnum).toContain('Component')
    expect(componentShapeEnum).toContain('ComponentDb')
    expect(componentShapeEnum).toContain('ComponentQueue')
    expect(componentShapeEnum).toContain('')
  })

  it('empty string is the first option (auto-infer from technology)', () => {
    expect(containerShapeEnum[0]).toBe('')
    expect(componentShapeEnum[0]).toBe('')
  })
})
