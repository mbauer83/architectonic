/**
 * The edit form's attributes, said as the patch the write path takes.
 *
 * The server keeps a key the body omits and removes one mapped to null, so a whole-map form has to
 * name what it took away. These pin that it does, and that it withdraws nothing it has no basis for.
 */
import { describe, expect, it } from 'vitest'
import { NO_ATTRIBUTES, attributesPatch, patchReplacing } from '../entityPropertiesPatch'

const row = (key: string, value = 'v', adHocType = 'string') => ({ key, value, adHocType })
const noSchema = () => false

describe('patchReplacing', () => {
  it('maps every key the new map no longer states to null', () => {
    expect(patchReplacing(['a', 'b'], { a: 1 })).toEqual({ a: 1, b: null })
  })

  it('is the new map unchanged when nothing was taken away', () => {
    expect(patchReplacing(['a'], { a: 1, c: 2 })).toEqual({ a: 1, c: 2 })
  })
})

describe('attributesPatch', () => {
  it('sends a removed attribute as null, so the save removes it', () => {
    const baseline = { propertyKeys: ['Owner', 'Retries'], attributeTypeKeys: [] }

    expect(attributesPatch(baseline, [row('Owner', 'Platform')], noSchema).properties)
      .toEqual({ Owner: 'Platform', Retries: null })
  })

  it('removes a removed attribute\'s ad-hoc type with it', () => {
    const baseline = { propertyKeys: ['Retries'], attributeTypeKeys: ['Retries'] }

    expect(attributesPatch(baseline, [], noSchema)).toEqual({
      properties: { Retries: null },
      attribute_types: { Retries: null },
    })
  })

  it('treats a renamed key as the old one removed and the new one added', () => {
    const baseline = { propertyKeys: ['Ownr'], attributeTypeKeys: [] }

    expect(attributesPatch(baseline, [row('Owner', 'Platform')], noSchema).properties)
      .toEqual({ Owner: 'Platform', Ownr: null })
  })

  it('withdraws an ad-hoc type the row went back to string from', () => {
    const baseline = { propertyKeys: ['Retries'], attributeTypeKeys: ['Retries'] }

    expect(attributesPatch(baseline, [row('Retries', '3', 'string')], noSchema).attribute_types)
      .toEqual({ Retries: null })
  })

  it('leaves a stored type alone where the schema types the row the form still shows', () => {
    const baseline = { propertyKeys: ['Priority'], attributeTypeKeys: ['Priority'] }
    const declared = (key: string) => key === 'Priority'

    expect(attributesPatch(baseline, [row('Priority', 'Must')], declared))
      .toEqual({ properties: { Priority: 'Must' } })
  })

  it('says nothing about types when there is nothing to say', () => {
    expect(attributesPatch(NO_ATTRIBUTES, [row('Owner')], noSchema)).toEqual({ properties: { Owner: 'v' } })
  })

  it('ignores a blank key, as an empty row the author never filled', () => {
    expect(attributesPatch(NO_ATTRIBUTES, [row('  ')], noSchema)).toEqual({ properties: {} })
  })
})
