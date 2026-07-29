import type { EntityAttributeDescriptor } from '../../domain'

export function metadataInputValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  return JSON.stringify(value)
}

function typedValue(raw: string, descriptor: EntityAttributeDescriptor | undefined): unknown {
  const value = raw.trim()
  if (descriptor?.type === 'integer') return Number.parseInt(value, 10)
  if (descriptor?.type === 'number') return Number(value)
  if (descriptor?.type === 'boolean') return value === 'true'
  if (descriptor?.type === 'array') return JSON.parse(value)
  return raw
}

export function metadataWireValues(
  values: Readonly<Record<string, string>>,
  descriptors: Readonly<Record<string, EntityAttributeDescriptor>>,
  originalValues: Readonly<Record<string, unknown>> = {},
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, value]) => value.trim() !== '')
      .map(([key, value]) => {
        const original = originalValues[key]
        if (!descriptors[key] && metadataInputValue(original) === value) return [key, original]
        return [key, typedValue(value, descriptors[key])]
      }),
  )
}
